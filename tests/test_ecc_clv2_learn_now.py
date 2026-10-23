"""learn_now writes the learner's instinct blocks to disk; a duplicate id inside one answer must not
silently overwrite (ledger pattern from harness2 core/ledger.py: a repeated label is an error, not a merge)."""
import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

_ECC = Path(__file__).resolve().parents[1] / "tools" / "ecc-clv2"
if not (os.environ.get("ECC_CLV2_SKILL_DIR") or (_ECC / "upstream" / "continuous-learning-v2").exists()):
    raise unittest.SkipTest("ECC continuous-learning-v2 upstream copy missing (set ECC_CLV2_SKILL_DIR)")
sys.path.insert(0, str(_ECC))
import learn_now  # noqa: E402

OBS = {"timestamp": "t", "event": "tool_start", "tool": "Bash", "session": "s", "project_id": "p", "project_name": "n", "input": "{}"}
BLOCK = "---\nid: {id}\ntrigger: when x\n---\n# T\n## Action\n{action}\n"


def answer(*blocks):
    return ("\n".join(f"<<<INSTINCT>>>\n{b}\n<<<END>>>" for b in blocks) + '\n{"status":"analysis_complete"}').encode()


class DuplicateIds(unittest.TestCase):
    def setUp(self):
        self.pdir = Path(tempfile.mkdtemp())
        (self.pdir / "observations.jsonl").write_text("\n".join([json.dumps(OBS)] * 25), "utf-8")

    def run_with(self, stdout: bytes):
        fake = mock.Mock(stdout=stdout, stderr=b"", returncode=0)
        with mock.patch.object(learn_now.subprocess, "run", return_value=fake):
            return learn_now.run(self.pdir, {"id": "p", "name": "n"})

    def test_same_id_twice_in_one_answer_keeps_first_and_logs(self):
        r = self.run_with(answer(BLOCK.format(id="a", action="First."), BLOCK.format(id="a", action="Second.")))
        self.assertIn("First.", (self.pdir / "instincts" / "personal" / "a.md").read_text("utf-8"))
        log = json.loads((self.pdir / "learn_now.log").read_text("utf-8").splitlines()[-1])
        self.assertEqual(log["duplicate_ids"], ["a"])
        self.assertIn("duplicate", r)

    def test_updating_an_existing_instinct_across_runs_is_allowed(self):
        self.run_with(answer(BLOCK.format(id="a", action="First.")))
        r = self.run_with(answer(BLOCK.format(id="a", action="Updated.")))
        self.assertIn("Updated.", (self.pdir / "instincts" / "personal" / "a.md").read_text("utf-8"))
        self.assertNotIn("duplicate", r)


if __name__ == "__main__":
    unittest.main()
