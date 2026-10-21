"""사업명 ↔ 예산서 구획 연결 검수 서버(kind: program_link). 표준 라이브러리만 사용.

  python link_server.py --dataset .local/program-link/dataset.json --votes .local/program-link/votes.json --rhwp <@rhwp/core>

dataset.json은 adapters/program_link/build_dataset.py + locate.mjs 가 만든다. 원본은 sha256이 맞을 때만 읽기 전용으로 내보낸다.
Human 판정은 --votes 파일에만 저장한다(studio-votes/v1, 데이터셋 해시에 묶임). 입력·연결 결과 파일은 수정하지 않는다.
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
UI = ROOT / 'ui' / 'link'
_spec = importlib.util.spec_from_file_location('studio_server', ROOT / 'studio_server.py')
studio = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(studio)
STATIC = {'/': (UI, 'index.html'), '/index.html': (UI, 'index.html'), '/app.js': (UI, 'app.js'), '/hwp-pane.js': (UI, 'hwp-pane.js'),
          '/styles.css': (UI, 'styles.css'), '/compare.html': (UI, 'compare.html'), '/hwp_locate.js': (ROOT / 'ui' / 'conflict', 'hwp_locate.js')}
MIME = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.wasm': 'application/wasm'}


def load_dataset(path):
    path = Path(path).resolve(); raw = path.read_bytes(); data = json.loads(raw.decode('utf-8'))
    if data.get('kind') != 'program_link' or not data.get('businesses'): raise ValueError('kind must be program_link with businesses')
    digest = hashlib.sha256(raw).hexdigest()
    segs = {s['id']: b['id'] for b in data['businesses'] for s in b['segments']}
    return {'path': path, 'dataset_sha256': digest, 'input_sha256': digest, 'data': data,
            'businesses': {b['id']: b for b in data['businesses']}, 'segments': segs}


def make_server(dataset, votes, rhwp, port=0, opener=None):
    opener = opener or os.startfile  # 기본 프로그램/탐색기에 열기 요청만 한다.
    ctx = load_dataset(dataset); votes = Path(votes).resolve(); rhwp = Path(rhwp).resolve() if rhwp else None
    if votes == ctx['path']: raise ValueError('votes must not overwrite the dataset')
    studio.read_votes(votes, ctx)
    docs, lock = ctx['data']['docs'], threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def send(self, status, payload, mime='application/json; charset=utf-8', cache='no-store'):
            raw = json.dumps(payload, ensure_ascii=False).encode('utf-8') if mime.startswith('application/json') else payload
            self.send_response(status); self.send_header('Content-Type', mime); self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', cache); self.send_header('X-Content-Type-Options', 'nosniff'); self.end_headers(); self.wfile.write(raw)

        def doc(self, doc_id, verify=True):
            d = docs.get(doc_id)
            if not d: raise KeyError('Unknown document')
            p = Path(d['path'])
            if verify and (not p.is_file() or studio.digest(p) != d['sha256']): raise ValueError('원본 파일 없음 또는 sha256 불일치')
            return p

        def do_GET(self):
            try:
                u = urlsplit(self.path); path = u.path
                if path == '/api/dataset': return self.send(200, ctx['data'])
                if path == '/api/votes': return self.send(200, studio.read_votes(votes, ctx)['votes'])
                if path == '/api/doc': return self.send(200, self.doc(parse_qs(u.query).get('id', [''])[0]).read_bytes(), 'application/octet-stream')
                if path in ('/rhwp/rhwp.js', '/rhwp/rhwp_bg.wasm'):
                    if not rhwp: return self.send(404, {'error': 'Start with --rhwp <@rhwp/core directory>'})
                    f = rhwp / path.rsplit('/', 1)[-1]; return self.send(200, f.read_bytes(), MIME[f.suffix], 'max-age=3600')
                if path in STATIC:
                    base, name = STATIC[path]; f = base / name; return self.send(200, f.read_bytes(), MIME[f.suffix])
                return self.send(404, {'error': 'Unknown path'})
            except KeyError as e: self.send(404, {'error': str(e)})
            except (OSError, ValueError) as e: self.send(400, {'error': str(e)})

        def do_POST(self):
            try:
                if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}' or self.headers.get('Origin') not in (None, f'http://127.0.0.1:{self.server.server_port}'):
                    return self.send(403, {'error': 'Use this local server origin'})
                if self.path not in ('/api/votes', '/api/open-source'): return self.send(404, {'error': 'Unknown API endpoint'})
                n = int(self.headers.get('Content-Length', '0'))
                if not 0 < n <= 100000: raise ValueError('Invalid request size')
                d = json.loads(self.rfile.read(n))
                if not isinstance(d, dict): raise ValueError('Expected object')
                if self.path == '/api/open-source':
                    if d.get('target') not in ('file', 'directory'): raise ValueError('target은 file 또는 directory')
                    p = self.doc(str(d.get('doc', '')), verify=d['target'] == 'file')
                    target = p if d['target'] == 'file' else p.parent
                    if d['target'] == 'directory' and not target.is_dir(): raise ValueError('폴더 없음: ' + str(target))
                    try: opener(str(target))
                    except OSError as e: return self.send(500, {'error': '열기 실패: ' + str(e)})
                    return self.send(200, {'opened': d['target'], 'path': str(target)})
                bid, sid = d.get('business_id'), d.get('segment_id')
                if bid not in ctx['businesses'] or (sid is not None and ctx['segments'].get(sid) != bid): raise ValueError('잘못된 검수 항목')
                choice, note = d.get('choice'), d.get('note', '')
                if choice not in ctx['data']['choices'] or not isinstance(note, str) or len(note) > 4000: raise ValueError('잘못된 선택지')
                if choice in ctx['data']['note_required_for'] and not note.strip(): raise ValueError(choice + '는 설명(연도·범위·구획) 필요')
                if studio.digest(ctx['path']) != ctx['dataset_sha256']: return self.send(409, {'error': 'Dataset changed; restart with a new --votes'})
                key = bid if sid is None else f'{bid}/{sid}'
                rec = {'business_id': bid, 'segment_id': sid, 'choice': choice, 'note': note.strip(), 'decided_by': 'human',
                       'submitted_via': 'local_review_ui', 'saved_at': datetime.now(timezone.utc).isoformat(),
                       'dataset_sha256': ctx['dataset_sha256']}
                with lock:
                    saved = studio.read_votes(votes, ctx); saved['votes'][key] = rec; studio.atomic_save(votes, saved)
                self.send(200, rec)
            except KeyError as e: self.send(404, {'error': str(e)})
            except (OSError, ValueError, TypeError) as e: self.send(400, {'error': str(e)})

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--dataset', type=Path, required=True); p.add_argument('--votes', type=Path, required=True)
    p.add_argument('--rhwp', type=Path); p.add_argument('--port', type=int, default=0)
    a = p.parse_args(); http = make_server(a.dataset, a.votes, a.rhwp, a.port)
    print(json.dumps({'url': f'http://127.0.0.1:{http.server_port}/', 'votes': str(a.votes.resolve())}, ensure_ascii=False), flush=True)
    try: http.serve_forever()
    except KeyboardInterrupt: pass
    finally: http.server_close()


if __name__ == '__main__': main()
