"""Leak tripwire (vendored from google-research/harness2 core/context.py, Apache-2.0): nothing but
metadata may reach a model. Fires on content-bearing fields, on parse_error 'raw' dumps, and on
answer-side markers in those fields; the user's own words in a correction are allowed."""
import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

_ECC = Path(__file__).resolve().parents[1] / "tools" / "ecc-clv2"
if not (os.environ.get("ECC_CLV2_SKILL_DIR") or (_ECC / "upstream" / "continuous-learning-v2").exists()):
    raise unittest.SkipTest("ECC continuous-learning-v2 upstream copy missing (set ECC_CLV2_SKILL_DIR)")
sys.path.insert(0, str(_ECC))
sys.path.insert(0, str(_ECC / "vendor_h2"))
import leak_guard, learn_now, eval_loop  # noqa: E402

OBS = {"timestamp": "t", "event": "tool_start", "tool": "Bash", "session": "s", "project_id": "p", "project_name": "n",
       "input": "{\"command\": \"ls 결과서/\"}"}  # a PATH mentioning the answer side is metadata: allowed
DONE = {**OBS, "event": "tool_complete", "output": ""}
CORR = {"timestamp": "t", "event": "user_correction", "session": "s", "cwd": "/x",
        "text": "결과서는 정답 전용이잖아, 입력 규칙에 섞지 마"}  # the user's rule itself: allowed


class Guard(unittest.TestCase):
    def test_metadata_only_records_pass(self):
        leak_guard.assert_records_metadata_only([OBS, DONE, CORR])

    def test_output_with_answer_marker_fires(self):
        with self.assertRaisesRegex(ValueError, "검토결과"):
            leak_guard.assert_records_metadata_only([{**DONE, "output": "... 유사·중복 검토결과서 1행 ..."}])

    def test_any_nonempty_output_fires(self):
        with self.assertRaisesRegex(ValueError, "output"):
            leak_guard.assert_records_metadata_only([{**DONE, "output": "hello"}])

    def test_parse_error_raw_dump_fires(self):
        with self.assertRaisesRegex(ValueError, "raw"):
            leak_guard.assert_records_metadata_only([{"timestamp": "t", "event": "parse_error", "raw": "{...2000 chars...}"}])

    def test_oversized_field_fires(self):
        with self.assertRaisesRegex(ValueError, "input"):
            leak_guard.assert_records_metadata_only([{**OBS, "input": "x" * 6000}])

    def test_vendored_tree_guard_matches_name_and_body(self):
        with self.assertRaisesRegex(ValueError, "NAME"):
            leak_guard.assert_tree_has_no_grader_verdicts({"정답/a.txt": "ok"})
        with self.assertRaisesRegex(ValueError, "silver"):
            leak_guard.assert_tree_has_no_grader_verdicts({"a.txt": "the SILVER labels"})
        leak_guard.assert_tree_has_no_grader_verdicts({"a.txt": "nothing here"})

    def test_markers_are_the_single_source_for_R3(self):
        for m in leak_guard.MARKERS:
            self.assertTrue(eval_loop.ANSWER_SIDE.search(m), m)


class LearnNowRefusesLeak(unittest.TestCase):
    def setUp(self):
        self.pdir = Path(tempfile.mkdtemp())
        (self.pdir / "observations.jsonl").write_text("\n".join([json.dumps(OBS)] * 25), "utf-8")

    def test_claude_is_not_called_when_a_record_leaks(self):
        (self.pdir / "corrections.jsonl").write_text(json.dumps({**DONE, "output": "검토결과 본문"}), "utf-8")
        with mock.patch.object(learn_now.subprocess, "run") as run:
            r = learn_now.run(self.pdir, {"id": "p", "name": "n"})
        self.assertTrue(r.startswith("skip (leak"), r)
        run.assert_not_called()
        self.assertEqual(list((self.pdir / ".observer-tmp").glob("*")) if (self.pdir / ".observer-tmp").exists() else [], [])
        log = json.loads((self.pdir / "learn_now.log").read_text("utf-8").splitlines()[-1])
        self.assertEqual(log["ok"], False)
        self.assertIn("leak", log["stderr"])

    def test_clean_records_reach_claude(self):
        fake = mock.Mock(stdout=b'{"status":"analysis_complete"}', stderr=b"", returncode=0)
        with mock.patch.object(learn_now.subprocess, "run", return_value=fake) as run:
            r = learn_now.run(self.pdir, {"id": "p", "name": "n"})
        self.assertTrue(r.startswith("ok"), r)
        run.assert_called_once()


class JudgeRefusesLeak(unittest.TestCase):
    def test_judge_not_called_when_evidence_leaks(self):
        tmp = Path(tempfile.mkdtemp())
        pdir = tmp / "projects" / "p1"
        (pdir / "instincts" / "personal").mkdir(parents=True)
        good = ("---\nid: g\ntrigger: when running tests\nconfidence: 0.5\ndomain: workflow\nsource: session-observation\n"
                "scope: project\nproject_id: p1\nproject_name: demo\n---\n\n# T\n\n## Action\nDo it.\n\n## Evidence\n"
                "- Observed 3 times in session aaaaaaaa-1111\n")
        (pdir / "instincts" / "personal" / "g.md").write_text(good, "utf-8")
        leaky = {"session": "aaaaaaaa-1111", "event": "tool_complete", "tool": "Read", "output": "검토결과서 내용"}
        (pdir / "observations.jsonl").write_text("\n".join([json.dumps(leaky)] * 4), "utf-8")
        with mock.patch.object(eval_loop, "judge") as judge:
            res = eval_loop.evaluate_project(pdir, {"id": "p1", "name": "demo"}, True)
        judge.assert_not_called()
        self.assertEqual(res[0]["status"], "candidate")
        self.assertIn("leak", res[0]["semantic"]["error"])


if __name__ == "__main__":
    unittest.main()
