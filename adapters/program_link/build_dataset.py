"""사업명 ↔ 예산서 구획 연결 검수 데이터셋을 만든다(위치 판정 전 단계). 입력은 읽기만 하고 sha256을 기록한다.

  python -I adapters/program_link/build_dataset.py <config.json> <out dataset.json>

단위: 사업 = linker.clean_answer_name(name)['search_name'] 이 같은 결과서 표기 묶음. 원래 표기·행정 표기는 모두 남긴다.
유사·중복 라벨과 판정 문구는 읽지도 싣지도 않는다(rows.json의 subject/comparison/source 필드만 사용).
"""
import hashlib
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(config_path, out_path):
    cfg = json.loads(Path(config_path).read_text(encoding='utf-8'))
    I = cfg['inputs']
    spec = importlib.util.spec_from_file_location('linker', I['linker_module'])
    linker = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(Path(I['linker_module']).parent))
    spec.loader.exec_module(linker)
    rows = {r['candidate_id']: r for r in json.loads(Path(I['rows']).read_text(encoding='utf-8'))}
    seg_groups = {e['endpoint_name']: e.get('segments', []) for e in json.loads(Path(I['segments']).read_text(encoding='utf-8'))} if I.get('segments') else {}
    links = {e['endpoint_name']: e for e in json.loads(Path(I['links']).read_text(encoding='utf-8'))}
    db = sqlite3.connect(f"file:{Path(I['budget_db']).as_posix()}?mode=ro", uri=True)
    title_field = cfg['locate']['budget_title_field']

    docs, businesses = {}, {}

    def doc(path, expected_sha=None, kind=''):
        p = Path(path)
        actual = sha(p) if p.is_file() else None
        key = 'D' + hashlib.sha256(str(p).encode('utf-8')).hexdigest()[:12]
        docs.setdefault(key, {'id': key, 'path': str(p), 'name': p.name, 'kind': kind, 'sha256': actual,
                              'expected_sha256': expected_sha, 'status': 'ok' if actual and (not expected_sha or actual == expected_sha) else ('missing' if not actual else 'sha_mismatch')})
        return key

    for rid in cfg['row_ids']:
        r = rows[rid]
        src = doc(r['source_path'], r['source_sha256'], 'judgment')
        for role, role_ko in cfg['roles'].items():
            name = r[role]
            c = linker.clean_answer_name(name)
            b = businesses.setdefault(c['search_name'], {'id': None, 'search_name': c['search_name'], 'mentions': [], 'segments': {}})
            b['mentions'].append({'row_id': rid, 'role': role_ko, 'original': name, 'scope': c['scope'],
                                  'administrative_metadata': c['administrative_metadata'], 'doc': src,
                                  'source_doc_year': r.get('source_doc_year'), 'source_folder': r.get('source_folder')})
            e = links.get(name) or {}
            for h in e.get('hits', []):
                k = tuple(h[x] for x in cfg['segment_dedupe_keys'])
                if k in b['segments']:  # 같은 키(설정 segment_dedupe_keys)의 구획은 한 탭으로 합치고 구조_id 목록과 본문을 모은다
                    seg = b['segments'][k]; seg['dup_rows'] += 1
                    if h['구조_id'] not in seg['merged_구조_ids']:
                        seg['merged_구조_ids'].append(h['구조_id'])
                        seg['content'] += [{'목적': (a or '').strip(), '내용': (bb or '').strip(), '원문': (raw or '').strip()}
                                           for a, bb, raw in db.execute('select 목적, 내용, 원문 from 사업내용 where 구조_id=?', (h['구조_id'],))]
                    continue
                f = db.execute(f'select 파일명, {title_field} from 사업 where 사업_id=?', (h['사업_id'],)).fetchone()
                content = [{'목적': (a or '').strip(), '내용': (bb or '').strip(), '원문': (raw or '').strip()}
                           for a, bb, raw in db.execute('select 목적, 내용, 원문 from 사업내용 where 구조_id=?', (h['구조_id'],))]
                fpath = Path(I['budget_root']) / str(h['회계연도']) / f[0] if f else None
                b['segments'][k] = {'구조_id': h['구조_id'], 'merged_구조_ids': [h['구조_id']], 'dup_rows': 0, '사업_id': h['사업_id'], '회계연도': h['회계연도'],
                                    '부처': h['부처'], '레벨명': h['레벨명'], '사업명': h['사업명'], '세부사업명': h['세부사업명'],
                                    'title': f[1] if f else None, 'content': content, 'link_reason': e.get('reason'), 'via_former_name': bool(h.get('via_former_name')),
                                    'doc': doc(fpath, None, 'budget') if fpath else None}
    out = []
    for n, b in enumerate(sorted(businesses.values(), key=lambda x: x['search_name']), 1):
        b['id'] = f'B{n:02d}'
        segs = sorted(b['segments'].values(), key=lambda s: (s['회계연도'], s['레벨명'] != '세부사업', s['구조_id']))
        for i, s in enumerate(segs, 1): s['id'] = f"{b['id']}-S{i:02d}"
        b['segments'] = segs
        # 탭 = 판정 단위. segments.json(segments.py merge_segments 결과)의 한 구획에 구조_id가 모두 들어가는 구획들을 한 탭으로 묶는다.
        groups = [g for m in b['mentions'] for g in seg_groups.get(m['original'], [])]
        tabs, used = [], set()
        for s in segs:
            if s['id'] in used: continue
            g = next((g for g in groups if set(s['merged_구조_ids']) <= set(g['구조_ids'])), None)
            members = [x['id'] for x in segs if g and set(x['merged_구조_ids']) <= set(g['구조_ids'])] or [s['id']]
            used.update(members)
            tabs.append({'id': members[0], 'members': members, 'merged_same_name': bool(g and g.get('merged_same_name')),
                         'scope_same': g.get('scope_same') if g else None, 'admin_siblings': g.get('admin_siblings', []) if g else [],
                         'other_siblings': g.get('other_siblings', []) if g else []})
        b['tabs'] = tabs
        out.append(b)
    data = {'kind': 'program_link', 'question': cfg['question'], 'choices': cfg['choices'], 'note_required_for': cfg['note_required_for'],
            'inputs': {k: {'path': v, 'sha256': sha(v) if Path(v).is_file() else None} for k, v in I.items() if k != 'budget_root'},
            'config': {'path': str(Path(config_path).resolve()), 'sha256': sha(config_path)},
            'locate_rules': cfg['locate'], 'aggregate_rules': cfg['aggregate_rules'], 'docs': docs, 'businesses': out,
            # JS 위치 판정이 search_rules.projection을 그대로 옮겼는지 확인할 대조표(linker가 sha256 검증 후 로드한 원 함수의 결과)
            'projection_check': {n: linker.projection(n) for n in sorted({x for b in out for x in [b['search_name']] + [m['original'] for m in b['mentions']] + [s['사업명'] for s in b['segments']] + [s['title'] or '' for s in b['segments']]})}}
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(data, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'businesses': len(out), 'segments': sum(len(b['segments']) for b in out), 'tabs': sum(len(b['tabs']) for b in out), 'docs': len(docs),
                      'budget_docs': sum(d['kind'] == 'budget' for d in docs.values()), 'doc_problems': [d['name'] for d in docs.values() if d['status'] != 'ok']}, ensure_ascii=False))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main(*sys.argv[1:3])
