"""차별점 인용 검수 데이터셋: agent가 뽑은 인용(quotes.json) + 판정서 원본 경로·sha256(rows.json) → ui/quote가 읽는 conflict 형식.

  python -I adapters/diff_quote/build_dataset.py <config.json> <out dataset.json>

입력은 읽기만 하고 sha256을 기록한다. 인용 문장은 원문 그대로 싣고, 유사·중복 라벨은 싣지 않는다.
"""
import hashlib
import json
import sys
from pathlib import Path


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(config_path, out_path):
    cfg = json.loads(Path(config_path).read_text(encoding='utf-8'))
    I = cfg['inputs']
    quotes = json.loads(Path(I['quotes']).read_text(encoding='utf-8'))
    rows = {r['candidate_id']: r for r in json.loads(Path(I['rows']).read_text(encoding='utf-8'))}
    cases = []
    for row in quotes['rows']:
        cid = row['candidate_id']; r = rows.get(cid)
        if not r: raise SystemExit(f'rows.json에 없는 candidate_id: {cid}')
        src = Path(r['source_path'])
        if src.name != Path(row['source_file']).name: raise SystemExit(f'{cid}: quotes.json 원본({Path(row["source_file"]).name})과 rows.json 원본({src.name})이 다름')
        cards = [{'id': f'q{i + 1}', 'title': f"인용 {i + 1} · {q.get('aspect', '')} · {cfg['about_labels'].get(q.get('about'), q.get('about', ''))}",
                  'quote': q['text'], 'location': '', 'context_before': q.get('context_before', ''), 'location_hint': q.get('location_hint', ''),
                  'aspect': q.get('aspect', ''), 'about': q.get('about', '')} for i, q in enumerate(row.get('quotes') or [])]
        cases.append({'pair_id': cid, 'new_business': r['subject'], 'comparison_business': r['comparison'],
                      'status': 'pending' if row['status'] != 'found' else 'found',
                      'reason': ('agent: ' + row['status'] + (' — ' + row['notes'] if row.get('notes') else '')) if row['status'] != 'found' else '',
                      'agent_notes': row.get('notes', ''), 'agent_status': row['status'],
                      'evidence': {'quote': cards[0]['quote'] if cards else r['subject'],
                                   'sources': [{'path': str(src), 'sha256': r['source_sha256'], 'table_index': r.get('source_folder', '')}]},
                      'audit_cards': cards})
    data = {'kind': 'conflict', 'subkind': 'diff_quote', 'question': cfg['question'],
            'inputs': {k: {'path': v, 'sha256': sha(v)} for k, v in I.items()}, 'quotes_meta': quotes.get('_meta'),
            'config': {'path': str(Path(config_path).resolve()), 'sha256': sha(config_path)}, 'cases': cases}
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(data, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'cases': len(cases), 'quotes': sum(len(c['audit_cards']) for c in cases),
                      'not_found': [c['pair_id'] for c in cases if c['agent_status'] != 'found']}, ensure_ascii=False))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main(*sys.argv[1:3])
