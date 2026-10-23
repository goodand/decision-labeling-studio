"""차별점 인용 검수: 의견서·결과서 원본(rhwp) 위에서 agent가 차별점으로 인용한 문장이 맞는지 인용마다 판정한다.
conflict_server.py 복사본(2026-10-23). 바뀐 것: 화면 폴더(ui/quote), 판정 단위(쌍 → 인용), 선택지.

Conflict review with native HWP/HWPX source rendering (rhwp) and XPath evidence jumps.

Python 3.10+, standard library only. Reuses studio_server.digest/read_votes/atomic_save and the
vote rules of uncertain_review_v1/server.py. Original documents and the rhwp binary stay outside
this repo: sources are referenced by absolute path + sha256, rhwp by --rhwp directory.

  python conflict_server.py --dataset human_conflicts.json --votes .local/conflict-votes.json --rhwp <@rhwp/core dir>
"""
import argparse
import hashlib
import importlib.util
import json
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
UI = ROOT / 'ui' / 'quote'
_spec = importlib.util.spec_from_file_location('studio_server', ROOT / 'studio_server.py')
studio = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(studio)

STATIC = {'/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js', '/rhwp-viewer.js': 'rhwp-viewer.js',
          '/hwp_locate.js': 'hwp_locate.js', '/pdf-source-viewer.js': 'pdf-source-viewer.js',
          '/pdf-source-viewer.css': 'pdf-source-viewer.css', '/legacy.css': 'legacy.css'}
MIME = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
        '.wasm': 'application/wasm'}
CHOICES = ('맞음', '틀림', '판단불가')          # 인용이 그 사업의 차별점으로 맞는가
NOTE_REQUIRED = ('틀림', '판단불가')


def load_dataset(path):
    """Dataset = list of conflict cases (human_conflicts.json form) or {"kind":"conflict","cases":[...]}."""
    path = Path(path).resolve()
    raw = path.read_bytes(); data = json.loads(raw.decode('utf-8-sig'))
    cases = data if isinstance(data, list) else data.get('cases') if isinstance(data, dict) and data.get('kind') == 'conflict' else None
    if not isinstance(cases, list) or not cases: raise ValueError('dataset must be a nonempty list of cases or {"kind":"conflict","cases":[...]}')
    index, sources = {}, {}
    for c in cases:
        pid = c.get('pair_id')
        if not isinstance(pid, str) or not pid or pid in index: raise ValueError('pair_id must be unique nonempty strings')
        index[pid] = c
        for i, s in enumerate((c.get('evidence') or {}).get('sources') or []):
            p, sha = Path(s.get('path', '')), s.get('sha256')
            ok = bool(sha) and p.is_file() and studio.digest(p) == sha
            sources[f'{pid}:{i}'] = {'path': p, 'sha256': sha, 'status': 'ok' if ok else 'missing_or_changed'}
    return {'path': path, 'dataset_sha256': hashlib.sha256(raw).hexdigest(), 'input_sha256': hashlib.sha256(raw).hexdigest(),
            'cases': cases, 'index': index, 'sources': sources}


def make_server(dataset, votes, rhwp, port=0, opener=None):
    opener = opener or os.startfile  # 기본 프로그램/탐색기에 열기 요청만 한다. 실행 중인 프로세스는 건드리지 않는다.
    context = load_dataset(dataset); votes = Path(votes).resolve(); rhwp = Path(rhwp).resolve() if rhwp else None
    if votes == context['path']: raise ValueError('votes must not overwrite the dataset')
    studio.read_votes(votes, context)
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def send(self, status, payload, mime='application/json; charset=utf-8', cache='no-store'):
            raw = json.dumps(payload, ensure_ascii=False).encode('utf-8') if mime.startswith('application/json') else payload
            self.send_response(status); self.send_header('Content-Type', mime); self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', cache); self.send_header('X-Content-Type-Options', 'nosniff'); self.end_headers(); self.wfile.write(raw)

        def source(self, query):
            key = parse_qs(query).get('row', [''])[0]
            key = key if ':' in key else key + ':0'
            s = context['sources'].get(key)
            if not s: raise KeyError('Unknown source row')
            if s['status'] != 'ok' or studio.digest(s['path']) != s['sha256']: raise ValueError('원본 파일 없음 또는 sha256 불일치')
            return s

        def do_GET(self):
            try:
                u = urlsplit(self.path); path = u.path
                if path == '/api/cases': return self.send(200, context['cases'])
                if path == '/api/votes': return self.send(200, {'votes': studio.read_votes(votes, context)['votes']})
                if path == '/api/source-info':
                    s = self.source(u.query); return self.send(200, {'format': s['path'].suffix.lower(), 'filename': s['path'].name})
                if path == '/api/source-native': return self.send(200, self.source(u.query)['path'].read_bytes(), 'application/octet-stream')
                if path in ('/rhwp/rhwp.js', '/rhwp/rhwp_bg.wasm'):
                    if not rhwp: return self.send(404, {'error': 'Start with --rhwp <@rhwp/core directory>'})
                    f = rhwp / path.rsplit('/', 1)[-1]; return self.send(200, f.read_bytes(), MIME[f.suffix], 'max-age=3600')
                if path in STATIC:
                    f = UI / STATIC[path]; return self.send(200, f.read_bytes(), MIME[f.suffix])
                return self.send(404, {'error': 'Unknown path'})
            except KeyError as exc: self.send(404, {'error': str(exc)})
            except (OSError, ValueError) as exc: self.send(400, {'error': str(exc)})

        def do_POST(self):
            try:
                if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}' or self.headers.get('Origin') not in (None, f'http://127.0.0.1:{self.server.server_port}'):
                    return self.send(403, {'error': 'Use this local server origin'})
                if self.path not in ('/api/votes', '/api/open-source'): return self.send(404, {'error': 'Unknown API endpoint'})
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 100000: raise ValueError('Invalid request size')
                d = json.loads(self.rfile.read(length))
                if self.path == '/api/open-source':
                    # 원본 파일 또는 폴더 열기(budget_name_eval_v1 source_preview.open_source_directory 방식 + 파일 열기).
                    # 경로는 데이터셋에서만 꺼내고 열기 직전에 sha256을 다시 확인한다.
                    if not isinstance(d, dict) or d.get('target') not in ('file', 'directory'): raise ValueError('target은 file 또는 directory')
                    if d['target'] == 'file':
                        target = self.source('row=' + str(d.get('row', '')))['path']
                    else:  # 파일이 없거나 바뀐 경우의 대안: 데이터셋에 적힌 경로의 폴더만 연다(파일 해시와 무관).
                        key = str(d.get('row', '')); src = context['sources'].get(key if ':' in key else key + ':0')
                        if not src: raise KeyError('Unknown source row')
                        target = src['path'].parent
                        if not target.is_dir(): raise ValueError('폴더 없음: ' + str(target))
                    try: opener(str(target))
                    except OSError as exc: return self.send(500, {'error': '열기 실패: ' + str(exc)})
                    return self.send(200, {'opened': d['target'], 'path': str(target)})
                if not isinstance(d, dict) or d.get('pair_id') not in context['index'] or d.get('choice') not in CHOICES: raise ValueError('잘못된 검수 항목')
                qids = [str(q.get('id') or f'q{i + 1}') for i, q in enumerate(context['index'][d['pair_id']].get('audit_cards') or [])]
                if d.get('quote_id') not in qids: raise ValueError('잘못된 인용 ID')
                if d['choice'] in NOTE_REQUIRED and not str(d.get('note', '')).strip(): raise ValueError('이유 필요(' + d['choice'] + ')')
                if studio.digest(context['path']) != context['dataset_sha256']: return self.send(409, {'error': 'Dataset changed; restart with a new --votes'})
                c = context['index'][d['pair_id']]
                record = {k: str(d.get(k, '')).strip() for k in ('pair_id', 'quote_id', 'choice', 'note')}
                record.update(saved_at=datetime.now(timezone.utc).isoformat(), submitted_via='local_review_ui', decided_by='human',
                              source_sha256=[s.get('sha256') for s in (c.get('evidence') or {}).get('sources') or []])
                with lock:
                    saved = studio.read_votes(votes, context); saved['votes'][d['pair_id'] + '/' + d['quote_id']] = record; studio.atomic_save(votes, saved)
                self.send(200, record)
            except KeyError as exc: self.send(404, {'error': str(exc)})
            except (OSError, ValueError, TypeError) as exc: self.send(400, {'error': str(exc)})

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--dataset', type=Path, required=True); p.add_argument('--votes', type=Path, required=True)
    p.add_argument('--rhwp', type=Path, help='@rhwp/core directory containing rhwp.js and rhwp_bg.wasm')
    p.add_argument('--port', type=int, default=0)
    a = p.parse_args(); http = make_server(a.dataset, a.votes, a.rhwp, a.port)
    print(json.dumps({'url': f'http://127.0.0.1:{http.server_port}/', 'votes': str(a.votes.resolve())}, ensure_ascii=False), flush=True)
    try: http.serve_forever()
    except KeyboardInterrupt: pass
    finally: http.server_close()


if __name__ == '__main__': main()
