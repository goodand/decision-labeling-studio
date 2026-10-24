"""Synonym table (STUDIO-ECC-022): an LLM may PROPOSE groups, a human APPROVES them, and only approved groups
are applied — deterministically — when matching. Validation is a rule; meaning is decided once per group."""
import json, os, sys, tempfile, unittest
from pathlib import Path

_ECC = Path(__file__).resolve().parents[1] / "tools" / "ecc-clv2"
sys.path.insert(0, str(_ECC))
import synonyms, repeat_instr  # noqa: E402


def table(groups):
    p = Path(tempfile.mkdtemp()) / "synonyms.json"
    p.write_text(json.dumps({"schema": "ecc-synonyms/v1", "groups": groups}, ensure_ascii=False), "utf-8")
    return p


EV = [{"date": "2026-10-24", "quote": "객관식, 폐쇄형 도 같은 의미로 사용했는데"}]
OK = {"id": "SYN-001", "canonical": "객관식 질문", "terms": ["객관식", "폐쇄형"], "status": "approved",
      "proposed_by": "llm", "approved_by": "human", "approved_on": "2026-10-24", "evidence": EV}


class Validate(unittest.TestCase):
    def test_shipped_table_is_valid(self):
        t = synonyms.load(synonyms.DEFAULT_PATH)
        self.assertIn("폐쇄형", t.terms_of("객관식"))

    def test_rejects_bad_tables(self):
        bad = [
            [{**OK, "status": "maybe"}],                                   # unknown status
            [{**OK, "evidence": []}],                                      # approved without evidence
            [{**OK, "approved_by": "llm"}],                                # only a human approves
            [OK, {**OK, "id": "SYN-002", "terms": ["폐쇄형", "선택형"]}],     # a term in two approved groups
            [OK, {**OK, "terms": ["다른", "단어"]}],                         # duplicate id
            [{**OK, "terms": ["객관식"]}],                                  # a group needs >= 2 terms
        ]
        for groups in bad:
            with self.assertRaises(ValueError, msg=groups):
                synonyms.load(table(groups))


class Apply(unittest.TestCase):
    def test_only_approved_groups_map(self):
        t = synonyms.load(table([OK, {"id": "SYN-002", "canonical": "더 읽기", "terms": ["more read", "상세하게 read"],
                                       "status": "proposed", "proposed_by": "llm", "evidence": EV}]))
        self.assertEqual(t.canon("폐쇄형"), t.canon("객관식"))
        self.assertEqual(t.canon("more read"), "more read")              # proposed: not applied
        self.assertEqual(t.canon("무관"), "무관")

    def test_repeat_detector_merges_approved_synonyms(self):
        t = synonyms.load(table([OK]))
        idx = repeat_instr.Index(synonyms=t)
        idx.add("s1", "폐쇄형 질문을 해라")
        idx.add("s2", "객관식 질문을 해라")
        idx.add("s3", "폐쇄형으로 물어봐")
        top = {r["phrase"]: r["sessions"] for r in idx.repeated(min_sessions=3)}
        self.assertEqual(top.get("객관식"), 3)                            # canonical = first term


if __name__ == "__main__":
    unittest.main()
