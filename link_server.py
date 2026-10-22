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


def _cond(count, n, spec):
    if spec == 'all': return count == n
    op, v = spec[:2], int(spec[2:])
    return {'>=': count >= v, '==': count == v, '<=': count <= v}[op]


def aggregate(choices, seg_ids, rules):
    """사업 전체 판정 = 구획별 Human 판정에서 계산(설정 aggregate_rules, 위에서부터 첫 일치). 반환 (결과|None, 규칙 id|'incomplete'|'undefined', 상세)."""
    missing = [s for s in seg_ids if s not in choices]
    if missing: return None, 'incomplete', {'미판정_구획': missing}
    labels = [choices[s] for s in seg_ids]; n = len(labels)
    for r in rules['rules']:
        if all(_cond(sum(labels.count(x) for x in k.split('+')), n, v) for k, v in r['require'].items()):
            return r['result'], r['id'], ({r['record'] + '_구획': [s for s in seg_ids if choices[s] == r['record']]} if r.get('record') else {})
    return None, 'undefined', {'판정_조합': sorted(set(labels))}


def tab_states(b, votes):
    """병합 탭(세부·내역 같은 이름) 판정 = 구성 구획 판정에서 이어받기. 형식 불변 votes를 읽기만 한다.
    none: 판정 없음 / own: 탭 자신의 판정만 / inherited: 구성 구획 판정이 모두 같음 / resolved: 탭에서 새로 저장해 이전 충돌을 덮음 / conflict: 구성 구획 판정이 다름(지우지 않음)."""
    out = {}
    for t in b.get('tabs') or [{'id': s['id'], 'members': [s['id']]} for s in b['segments']]:
        mv = {m: votes[f"{b['id']}/{m}"] for m in t['members'] if f"{b['id']}/{m}" in votes}
        members = {m: v['choice'] for m, v in mv.items()}
        if not mv: st, ch = 'none', None
        elif len(set(members.values())) == 1: st, ch = ('own' if list(mv) == [t['id']] else 'inherited'), next(iter(members.values()))
        elif t['id'] in mv and mv[t['id']]['saved_at'] >= max(v['saved_at'] for v in mv.values()): st, ch = 'resolved', members[t['id']]
        else: st, ch = 'conflict', None
        out[t['id']] = {'choice': ch, 'status': st, 'members': members}
    return out


def derive(bid, ctx, saved):
    b = ctx['businesses'][bid]; tabs = tab_states(b, saved['votes']); ids = list(tabs)
    ch = {k: t['choice'] for k, t in tabs.items() if t['choice']}
    conflicts = [k for k, t in tabs.items() if t['status'] == 'conflict']
    res, rule, detail = (None, 'conflict', {'충돌_탭': conflicts}) if conflicts else aggregate(ch, ids, ctx['data']['aggregate_rules'])
    legacy = saved['votes'].get(bid)  # 이전 방식(사람이 직접 입력한 사업 전체 판정)은 지우지 않고 대조만 한다
    return {'result': res, 'rule': rule, 'status': 'complete' if res else rule, 'detail': detail, 'judged': len(ch), 'segments': len(ids),
            'rules_version': ctx['data']['aggregate_rules']['version'], 'derived_by': 'code',
            'tabs': tabs, 'legacy_human_choice': legacy['choice'] if legacy else None, 'legacy_differs': bool(legacy and res and legacy['choice'] != res)}


def load_dataset(path):
    path = Path(path).resolve(); raw = path.read_bytes(); data = json.loads(raw.decode('utf-8'))
    if data.get('kind') != 'program_link' or not data.get('businesses'): raise ValueError('kind must be program_link with businesses')
    digest = hashlib.sha256(raw).hexdigest()
    # 판정 대상은 탭(병합 구획이면 대표 구획 ID). 탭 정보가 없으면 구획마다 한 탭.
    segs = {t['id']: b['id'] for b in data['businesses'] for t in (b.get('tabs') or [{'id': s['id']} for s in b['segments']])}
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
                if path == '/api/derived':
                    saved = studio.read_votes(votes, ctx); return self.send(200, {bid: derive(bid, ctx, saved) for bid in ctx['businesses']})
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
                if bid not in ctx['businesses'] or ctx['segments'].get(sid) != bid: raise ValueError('구획(탭) 단위로만 판정한다. 사업 전체는 구획 판정에서 계산된다')
                choice, note = d.get('choice'), d.get('note', '')
                if choice not in ctx['data']['choices'] or not isinstance(note, str) or len(note) > 4000: raise ValueError('잘못된 선택지')
                if choice in ctx['data']['note_required_for'] and not note.strip(): raise ValueError(choice + '는 설명(연도·범위·구획) 필요')
                if studio.digest(ctx['path']) != ctx['dataset_sha256']: return self.send(409, {'error': 'Dataset changed; restart with a new --votes'})
                key = f'{bid}/{sid}'
                rec = {'business_id': bid, 'segment_id': sid, 'choice': choice, 'note': note.strip(), 'decided_by': 'human',
                       'submitted_via': 'local_review_ui', 'saved_at': datetime.now(timezone.utc).isoformat(),
                       'dataset_sha256': ctx['dataset_sha256']}  # 형식은 기존 그대로(2026-10-22 사용자 정정: 스키마 변경 금지)
                with lock:
                    saved = studio.read_votes(votes, ctx); saved['votes'][key] = rec; studio.atomic_save(votes, saved)  # 사업 전체는 저장하지 않고 /api/derived 에서 표시용으로만 계산
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
