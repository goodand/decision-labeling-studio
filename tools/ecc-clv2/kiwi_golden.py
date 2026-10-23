"""Regenerate tests/fixtures/kiwi_golden.json: the pinned Kiwi's tokens for the fixed correction set.
Run only together with a deliberate PIN change in kiwi_server.py (needs the resident server up)."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capture_correction as cc, kiwi_server  # noqa: E402  (reuse the hook's own tokenizer path)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
from test_ecc_clv2_kiwi_negation import YES, NO  # noqa: E402  (the fixed set lives in one place)

if __name__ == "__main__":
    assert kiwi_server.identity() == kiwi_server.PIN, (kiwi_server.identity(), kiwi_server.PIN)
    out = {"pin": kiwi_server.PIN, "tokens": {t: cc._tokens_from_server(t) for t in YES + NO}}
    dst = ROOT / "tests" / "fixtures" / "kiwi_golden.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print("wrote", dst, len(out["tokens"]), "texts")
