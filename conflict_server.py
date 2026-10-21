"""Conflict review with native HWP/HWPX source rendering (rhwp) and XPath evidence jumps.

Python 3.10+, standard library only. Reuses studio_server.digest/read_votes/atomic_save and the
vote rules of uncertain_review_v1/server.py. Original documents and the rhwp binary stay outside
this repo: sources are referenced by absolute path + sha256, rhwp by --rhwp directory.

  python conflict_server.py --dataset human_conflicts.json --votes .local/conflict-votes.json --rhwp <@rhwp/core dir>
"""
import argparse
import hashlib
import importlib.util
import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
UI = ROOT / 'ui' / 'conflict'
_spec = importlib.util.spec_from_file_location('studio_server', ROOT / 'studio_server.py')
studio = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(studio)

STATIC = {'/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js', '/rhwp-viewer.js': 'rhwp-viewer.js',
          '/hwp_locate.js': 'hwp_locate.js', '/pdf-source-viewer.js': 'pdf-source-viewer.js',
          '/pdf-source-viewer.css': 'pdf-source-viewer.css', '/legacy.css': 'legacy.css'}
MIME = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
        '.wasm': 'application/wasm'}
LABELS = ('유사중복 있음', '유사중복 없음', '판단불가')
CHOICES = ('accurate', 'corrected', 'uncertain')


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


def make_server(dataset, votes, rhwp, port=0):
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
                if self.path != '/api/votes': return self.send(404, {'error': 'Unknown API endpoint'})
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 100000: raise ValueError('Invalid request size')
                d = json.loads(self.rfile.read(length))
                if not isinstance(d, dict) or d.get('pair_id') not in context['index'] or d.get('choice') not in CHOICES: raise ValueError('잘못된 검수 항목')
                if any(not isinstance(d.get(k), str) or not d[k].strip() for k in ('subject', 'comparison', 'label', 'scope')): raise ValueError('필수 입력 누락')
                if d['label'] not in LABELS: raise ValueError('잘못된 라벨')
                if d['choice'] == 'uncertain' and not str(d.get('note', '')).strip(): raise ValueError('판단불가 사유 필요')
                if studio.digest(context['path']) != context['dataset_sha256']: return self.send(409, {'error': 'Dataset changed; restart with a new --votes'})
                c = context['index'][d['pair_id']]
                record = {k: str(d.get(k, '')).strip() for k in ('pair_id', 'subject', 'comparison', 'label', 'scope', 'choice', 'note')}
                record.update(saved_at=datetime.now(timezone.utc).isoformat(), submitted_via='local_review_ui', decided_by='human',
                              source_sha256=[s.get('sha256') for s in (c.get('evidence') or {}).get('sources') or []])
                with lock:
                    saved = studio.read_votes(votes, context); saved['votes'][d['pair_id']] = record; studio.atomic_save(votes, saved)
                self.send(200, record)
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
