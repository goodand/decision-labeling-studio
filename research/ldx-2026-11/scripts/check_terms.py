"""용어 설명 규칙 판정.

사용: python scripts/check_terms.py <round.json> [terms.yaml]
round.json: [{"id": "T01", "term": "...", "explanation": "..."}]
판정: must의 모든 그룹에서 단어가 하나 이상 나오고, must_not이 하나도 없으면 PASS.
LLM 판정은 쓰지 않는다. 결과 표와 실패 목록을 출력한다.
"""
import json
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")


def judge(expl: str, rule: dict) -> tuple[bool, list[str]]:
    text = expl.lower()
    why = []
    for group in rule.get("must", []):
        if not any(w.lower() in text for w in group):
            why.append("누락: " + "|".join(group[:4]))
    for w in rule.get("must_not", []):
        if w.lower() in text:
            why.append("오해 신호: " + w)
    return (not why), why


def main() -> None:
    rnd = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    terms_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parents[1] / "docs/glossary/terms.yaml"
    rules = {t["id"]: t for t in yaml.safe_load(terms_path.read_text(encoding="utf-8"))["terms"]}
    fails = 0
    for r in rnd:
        ok, why = judge(r["explanation"], rules[r["id"]])
        fails += not ok
        print(f'{r["id"]} {"PASS" if ok else "FAIL"} | {r["term"]} | {"; ".join(why)}')
    print(f"합계: {len(rnd) - fails}/{len(rnd)} 통과")


if __name__ == "__main__":
    main()
