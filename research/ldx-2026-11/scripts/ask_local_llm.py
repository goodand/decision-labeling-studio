"""로컬 LLM(LM Studio, OpenAI 호환 API)에 용어 설명을 받아 규칙 판정한다.

사용: python scripts/ask_local_llm.py <model_id> <samples> <out.json> [terms.json|names.yaml]
용어는 docs/glossary/final_terms.json, 판정은 scripts/check_terms.py의 judge()와 같은 규칙.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_terms import judge  # noqa: E402

PROMPT = (
    "아래 이름(또는 용어) 각각의 뜻을 한국어 1~2문장으로 설명하세요. 추가 맥락은 없습니다. "
    "이 용어를 처음 본 사람이 가장 자연스럽게 이해할 뜻으로 설명하세요. 모르면 추측해서라도 설명하세요.\n\n"
    '출력은 JSON 배열 하나만, 다른 말 없이: [{"id": "...", "term": "...", "explanation": "..."}]\n\n'
)


def ask(model: str, terms: list[dict]) -> list[dict]:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT + "\n".join(f'{t["id"]} {t["term"]}' for t in terms)}],
        "temperature": 0.7,
    }
    req = urllib.request.Request(
        "http://127.0.0.1:1234/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    text = json.load(urllib.request.urlopen(req, timeout=900))["choices"][0]["message"]["content"]
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    return json.loads(text[text.index("[") : text.rindex("]") + 1])


def main() -> None:
    model, n, out = sys.argv[1], int(sys.argv[2]), Path(sys.argv[3])
    src = Path(sys.argv[4]) if len(sys.argv) > 4 else ROOT / "docs/glossary/final_terms.json"
    raw = src.read_text(encoding="utf-8")
    terms = __import__("yaml").safe_load(raw)["terms"] if src.suffix == ".yaml" else json.loads(raw)
    rules = {t["id"]: t for t in terms}
    samples = []
    for k in range(n):
        order = terms if k % 2 == 0 else list(reversed(terms))
        samples.append(ask(model, order))
        print(f"표본 {k + 1}/{n} 수신", flush=True)
    out.write_text(json.dumps(samples, ensure_ascii=False, indent=1), encoding="utf-8")
    for t in terms:
        rows = [next((i.get("explanation", "") for i in s if i.get("id") == t["id"]), "") for s in samples]
        res = [judge(e, rules[t["id"]]) for e in rows]
        bad = [f'{e[:60]}… [{"; ".join(w)}]' for e, (ok, w) in zip(rows, res) if not ok]
        print(f'{t["id"]} {sum(ok for ok, _ in res)}/{n} {t["term"]}' + ("" if not bad else " | " + " / ".join(bad)))


if __name__ == "__main__":
    main()
