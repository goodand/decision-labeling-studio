"""Automation: correction capture (rule-based), throttle, auto-promotion to a digest/memory file."""
import json, sys, tempfile, unittest
from pathlib import Path

import os, unittest
from pathlib import Path as _P
_ECC = _P(__file__).resolve().parents[1] / "tools" / "ecc-clv2"
if not (os.environ.get("ECC_CLV2_SKILL_DIR") or (_ECC / "upstream" / "continuous-learning-v2").exists()):
    raise unittest.SkipTest("ECC continuous-learning-v2 upstream copy missing (set ECC_CLV2_SKILL_DIR)")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "ecc-clv2"))
import capture_correction, auto_learn  # noqa: E402


class CorrectionDetect(unittest.TestCase):
    def test_korean_correction_markers(self):
        yes = ["그게 아니라 원본 코드를 import 해야지", "결과서는 정답 전용이잖아, 입력 규칙에 섞지 마",
               "출력 덮어쓰지 말고 새 폴더에 저장해", "스크립트 새로 쓰지 말고 재사용해"]
        no = ["진행해", "git status 보여줘", "어떤 directory가 더 적절할지 찾아봐"]
        for t in yes:
            self.assertTrue(capture_correction.is_correction(t), t)
        for t in no:
            self.assertFalse(capture_correction.is_correction(t), t)

    def test_record_is_bounded_and_file_safe(self):
        rec = capture_correction.make_record("s1", "D:/x", "아니 " + "가" * 1000 + " D:/x/예산서.hwpx")
        self.assertLessEqual(len(rec["text"]), capture_correction.MAX_CHARS)
        self.assertNotIn(".hwpx", rec["text"])  # document file refs are masked


class AutoLearnFlow(unittest.TestCase):
    def setUp(self):
        self.store = Path(tempfile.mkdtemp())
        auto_learn.STORE = self.store
        auto_learn.DIGEST = self.store / "digest.md"
        auto_learn.HABITS = self.store / "habits.md"
        pdir = self.store / "projects" / "p1"
        (pdir / "instincts" / "personal").mkdir(parents=True)
        (self.store / "projects.json").write_text(json.dumps({"p1": {"id": "p1", "name": "demo"}}), "utf-8")
        (pdir / "observations.jsonl").write_text("\n".join(json.dumps({"session": "s"}) for _ in range(30)), "utf-8")

    def test_throttle_needs_new_observations(self):
        pdir = self.store / "projects" / "p1"
        self.assertTrue(auto_learn.due(pdir))
        auto_learn.mark_done(pdir)
        self.assertFalse(auto_learn.due(pdir))
        with open(pdir / "observations.jsonl", "a", encoding="utf-8") as f:
            f.write("\n" + "\n".join(json.dumps({"session": "s"}) for _ in range(auto_learn.MIN_NEW)))
        self.assertTrue(auto_learn.due(pdir))

    def test_default_cycle_uses_no_llm_judge(self):
        """User rule (2026-10-23): verification by rules + human, no LLM judge. The unattended cycle must
        run the gate with semantic=False unless ECC_LEARN_SEMANTIC=1 is set explicitly."""
        import os
        from unittest import mock
        seen = {}
        with mock.patch.object(auto_learn.learn_now, "run", lambda pdir, meta: "ok"), \
             mock.patch.object(auto_learn.eval_loop, "evaluate_project",
                               lambda pdir, meta, semantic: seen.update(semantic=semantic) or []), \
             mock.patch.dict(os.environ):  # restore: other test modules share these modules
            os.environ.pop("ECC_LEARN_SEMANTIC", None)
            auto_learn.main(["--force"])
        self.assertIs(seen["semantic"], False)

    def test_active_goes_to_habits_and_manual_to_digest(self):
        status = [{"file": "a.md", "status": "active", "rules": {}, "evidence": {}, "semantic": {"verdicts": ["accept"] * 3}},
                  {"file": "b.md", "status": "candidate", "rules": {}, "evidence": {}, "semantic": {"verdicts": ["manual_review"] * 3}}]
        pdir = self.store / "projects" / "p1"
        for n in ("a", "b"):
            (pdir / "instincts" / "personal" / f"{n}.md").write_text(
                f"---\nid: {n}\ntrigger: when {n}\nconfidence: 0.7\n---\n# {n.upper()}\n## Action\nDo {n}.\n", "utf-8")
        auto_learn.publish({"demo": status}, {"p1": {"id": "p1", "name": "demo"}})
        self.assertIn("Do a.", auto_learn.HABITS.read_text("utf-8"))
        self.assertNotIn("Do b.", auto_learn.HABITS.read_text("utf-8"))
        self.assertIn("b.md", auto_learn.DIGEST.read_text("utf-8"))
        auto_learn.publish({"demo": status}, {"p1": {"id": "p1", "name": "demo"}})  # idempotent
        self.assertEqual(auto_learn.HABITS.read_text("utf-8").count("Do a."), 1)


if __name__ == "__main__":
    unittest.main()
