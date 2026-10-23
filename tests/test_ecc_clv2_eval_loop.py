"""Rule gates must reject bad instincts (run with --no-semantic, synthetic store)."""
import json, sys, tempfile, unittest
from pathlib import Path

import os, unittest
from pathlib import Path as _P
_ECC = _P(__file__).resolve().parents[1] / "tools" / "ecc-clv2"
if not (os.environ.get("ECC_CLV2_SKILL_DIR") or (_ECC / "upstream" / "continuous-learning-v2").exists()):
    raise unittest.SkipTest("ECC continuous-learning-v2 upstream copy missing (set ECC_CLV2_SKILL_DIR)")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "ecc-clv2"))
import eval_loop  # noqa: E402

GOOD = """---
id: {id}
trigger: when {trig}
confidence: 0.5
domain: workflow
source: session-observation
scope: project
project_id: p1
project_name: demo
---

# T

## Action
Do the thing.

## Evidence
- Observed 3 times in session {sess}
"""


class GateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        eval_loop.STORE = self.tmp
        (self.tmp / "projects.json").write_text(json.dumps({"p1": {"id": "p1", "name": "demo-labeling-studio"}}), "utf-8")
        pdir = self.tmp / "projects" / "p1"
        (pdir / "instincts" / "personal").mkdir(parents=True)
        obs = [{"session": "aaaaaaaa-1111"}] * 4 + [{"session": "bbbbbbbb-2222"}] * 1
        (pdir / "observations.jsonl").write_text("\n".join(json.dumps(o) for o in obs), "utf-8")
        cases = {
            "good": GOOD.format(id="good", trig="running unit tests before commit", sess="aaaaaaaa-1111"),
            "docext": GOOD.format(id="docext", trig="reading budget files", sess="aaaaaaaa-1111") + "See D:/x/예산서.hwpx\n",
            "answer": GOOD.format(id="answer", trig="mapping programs using 결과서 labels", sess="aaaaaaaa-1111"),
            "code": GOOD.format(id="code", trig="editing adapters", sess="aaaaaaaa-1111") + "```py\nx=1\n```\n",
            "thin": GOOD.format(id="thin", trig="opening dashboards quickly", sess="bbbbbbbb-2222"),
            "ghost": GOOD.format(id="ghost", trig="deploying staging servers", sess="cccccccc-3333"),
            "pname": GOOD.format(id="pname", trig="committing in demo labeling studio", sess="aaaaaaaa-1111"),
            "multi": GOOD.format(id="multi", trig="citing several sessions at once", sess="aaaaaaaa-1111").replace(
                "in session aaaaaaaa-1111", "across sessions aaaaaaaa-1111, bbbbbbbb-2222 and aaaaaaaa-1111"),
            "pname2": GOOD.format(id="pname2", trig="screenshots in demo labeling studio", sess="aaaaaaaa-1111"),
        }
        for k, v in cases.items():
            (pdir / "instincts" / "personal" / f"{k}.md").write_text(v, "utf-8")

    def test_gates(self):
        res = {r["file"][:-3]: r for r in eval_loop.evaluate_project(self.tmp / "projects" / "p1",
                                                                     {"id": "p1", "name": "demo-labeling-studio"}, False)}
        self.assertEqual(res["good"]["status"], "candidate")  # rules pass, single session -> not active
        self.assertFalse(res["docext"]["rules"]["R2_no_code_or_doc_text"])
        self.assertFalse(res["code"]["rules"]["R2_no_code_or_doc_text"])
        self.assertFalse(res["answer"]["rules"]["R3_no_answer_side_rule"])
        self.assertFalse(res["thin"]["rules"]["R4_evidence_sessions_exist"])   # below noise floor
        self.assertFalse(res["ghost"]["rules"]["R4_evidence_sessions_exist"])  # cited session absent
        self.assertEqual(res["multi"]["evidence"]["cited_sessions"], ["aaaaaaaa-1111", "bbbbbbbb-2222"])
        self.assertTrue(res["pname"]["rules"]["R5_not_duplicate"])  # shared project name is not overlap
        for k in ("docext", "code", "answer", "thin", "ghost"):
            self.assertEqual(res[k]["status"], "rejected", k)


    def test_semantic_contract(self):
        meta = {"id": "p1", "name": "demo-labeling-studio"}
        for verdict, expected in ((None, "candidate"), ("accept", "active"), ("reject", "rejected"),
                                  ("manual_review", "candidate")):
            reply = {"bad": "shape"} if verdict is None else {"verdict": verdict, "reason": "r", "evidence_ids": [0]}
            eval_loop.judge = lambda text, evidence, _r=reply: _r
            res = {r["file"][:-3]: r for r in eval_loop.evaluate_project(self.tmp / "projects" / "p1", meta, True)}
            self.assertEqual(res["good"]["status"], expected, verdict)


    def test_archive_counts_as_evidence(self):  # E3
        pdir = self.tmp / "projects" / "p1"
        (pdir / "observations.archive").mkdir()
        (pdir / "observations.archive" / "observations-1.jsonl").write_text(
            "\n".join(json.dumps({"session": "bbbbbbbb-2222"}) for _ in range(3)), "utf-8")
        res = {r["file"][:-3]: r for r in eval_loop.evaluate_project(pdir, {"id": "p1", "name": "demo-labeling-studio"}, False)}
        self.assertTrue(res["thin"]["rules"]["R4_evidence_sessions_exist"])

    def test_three_judgements_must_agree(self):  # E1
        meta = {"id": "p1", "name": "demo-labeling-studio"}
        for seq, expected in ((["accept"] * 3, "active"), (["accept", "accept", "manual_review"], "candidate"),
                              (["accept", "reject", "accept"], "rejected")):
            it = iter(seq * 20)
            eval_loop.judge = lambda text, evidence: {"verdict": next(it), "reason": "r", "evidence_ids": [0]}
            res = {r["file"][:-3]: r for r in eval_loop.evaluate_project(self.tmp / "projects" / "p1", meta, True)}
            self.assertEqual(res["good"]["status"], expected, seq)


if __name__ == "__main__":
    unittest.main()
