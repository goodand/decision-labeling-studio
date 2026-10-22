"""데이터셋을 다시 만든 뒤 기존 Human 판정을 새 리비전으로 옮긴다. 기록은 한 글자도 바꾸지 않는다(형식 studio-votes/v1 그대로).

  python -I adapters/program_link/carry_votes.py <old votes.json> <new dataset.json> <new votes.json>

- old votes 파일은 읽기만 한다(백업은 호출 전에 복사). 각 기록의 dataset_sha256은 원래 값 그대로라 저장 당시 리비전을 구분할 수 있다.
- 새 데이터셋에 없는 구획 ID의 기록도 지우지 않고 그대로 옮긴다(화면에서는 쓰이지 않음, 보고에 목록 출력).
"""
import hashlib
import json
import sys
from pathlib import Path


def main(old_votes, new_dataset, new_votes):
    old = json.loads(Path(old_votes).read_text(encoding='utf-8'))
    if old.get('schema') != 'studio-votes/v1': raise SystemExit('unexpected votes schema')
    out = Path(new_votes)
    if out.exists() and out.resolve() != Path(old_votes).resolve(): raise SystemExit('new votes file already exists')
    raw = Path(new_dataset).read_bytes(); data = json.loads(raw.decode('utf-8'))
    known = {f"{b['id']}/{s['id']}" for b in data['businesses'] for s in b['segments']} | {b['id'] for b in data['businesses']}
    new = {'schema': 'studio-votes/v1', 'input_sha256': hashlib.sha256(raw).hexdigest(), 'decisions': old.get('decisions', {}), 'votes': old['votes']}
    out.write_text(json.dumps(new, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'carried': len(old['votes']), 'not_in_new_dataset': sorted(k for k in old['votes'] if k not in known),
                      'old_input_sha256': old.get('input_sha256'), 'new_input_sha256': new['input_sha256']}, ensure_ascii=False))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main(*sys.argv[1:4])
