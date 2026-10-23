"""PreToolUse guard: whole-file Read of .pdf/.hwp/.hwpx must be blocked (exit 2), others allowed."""
import json, subprocess, sys, unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "tools" / "ecc-clv2" / "block_doc_read.py"


def run(payload):
    return subprocess.run([sys.executable, "-X", "utf8", "-I", str(HOOK)], input=json.dumps(payload).encode("utf-8"),
                          capture_output=True, timeout=30)


class BlockTest(unittest.TestCase):
    def test_blocked(self):
        for p in (r"D:\x\예산서.pdf", "D:/x/a.HWP", r"C:\y\b.hwpx", "D:/x/c.Pdf"):
            r = run({"tool_name": "Read", "tool_input": {"file_path": p}})
            self.assertEqual(r.returncode, 2, p)
            self.assertIn("차단", r.stderr.decode("utf-8"))

    def test_allowed(self):
        for p in ("D:/x/a.md", "D:/x/a.pdf.txt", "D:/x/hwpx_notes.json", "D:/x/a.xlsx"):
            self.assertEqual(run({"tool_name": "Read", "tool_input": {"file_path": p}}).returncode, 0, p)
        self.assertEqual(run({"tool_name": "Grep", "tool_input": {"path": "D:/x/a.pdf"}}).returncode, 0)

    def test_bad_input_fails_open_without_crash(self):
        r = subprocess.run([sys.executable, "-I", str(HOOK)], input=b"not json", capture_output=True, timeout=30)
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
