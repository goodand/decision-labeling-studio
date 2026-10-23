"""OS branching for the ecc-clv2 hooks: one store for every script, bash path forms, the observe lock."""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

_ECC = Path(__file__).resolve().parents[1] / "tools" / "ecc-clv2"
sys.path.insert(0, str(_ECC))
import platform_compat as pc  # noqa: E402


class StoreDir(unittest.TestCase):
    def test_env_order(self):
        with mock.patch.dict(os.environ, {"ECC_CLV2_STORE_WIN": "", "ECC_CLV2_STORE": ""}):
            self.assertEqual(pc.store_dir(), pc.DEFAULT_STORE)
        with mock.patch.dict(os.environ, {"ECC_CLV2_STORE_WIN": "", "ECC_CLV2_STORE": "/tmp/s2"}):
            self.assertEqual(pc.store_dir(), Path(pc.from_bash_path("/tmp/s2")))
        with mock.patch.dict(os.environ, {"ECC_CLV2_STORE_WIN": "/tmp/s1", "ECC_CLV2_STORE": "/tmp/s2"}):
            self.assertEqual(pc.store_dir(), Path("/tmp/s1"))

    def test_every_script_reads_the_same_store(self):
        """capture_correction writes where learn_now/eval_loop/auto_learn read (they used to disagree)."""
        store = tempfile.mkdtemp()
        code = ("import capture_correction, learn_now, observe_meta, platform_compat;"
                "print(capture_correction.STORE, learn_now.STORE, platform_compat.store_dir(), sep='|')")
        out = subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(_ECC)!r}); {code}"],
                             env=dict(os.environ, ECC_CLV2_STORE_WIN=store), capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(set(out.stdout.strip().split("|")), {store})


class BashPaths(unittest.TestCase):
    def test_windows_drive_round_trip(self):
        with mock.patch.object(pc, "IS_WIN", True):
            self.assertEqual(pc.to_bash_path("C:\\Users\\me\\x"), "/c/Users/me/x")
            self.assertEqual(pc.from_bash_path("/c/Users/me/x"), "c:/Users/me/x")

    def test_posix_unchanged(self):
        with mock.patch.object(pc, "IS_WIN", False):
            self.assertEqual(pc.to_bash_path("/Users/me/x"), "/Users/me/x")
            self.assertEqual(pc.from_bash_path("/c/x"), "/c/x")

    def test_bash_exists(self):
        self.assertTrue(os.environ.get("ECC_GIT_BASH") or Path(pc.bash_path()).exists())


class Lock(unittest.TestCase):
    def test_second_holder_times_out(self):
        path = Path(tempfile.mkdtemp()) / ".observe.lock"
        holder = subprocess.Popen([sys.executable, "-I", "-c",
                                   f"import sys,time; sys.path.insert(0, {str(_ECC)!r}); import platform_compat as pc\n"
                                   f"with open({str(path)!r}, 'a+b') as f, pc.file_lock(f, 5) as ok:\n"
                                   f"    print(ok, flush=True); time.sleep(3)"],
                                  stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(holder.stdout.readline().strip(), "True")
            with open(path, "a+b") as f, pc.file_lock(f, 0.3) as ok:
                self.assertFalse(ok)
        finally:
            holder.wait(10)
        with open(path, "a+b") as f, pc.file_lock(f, 1) as ok:
            self.assertTrue(ok)


class ObserveMetaHook(unittest.TestCase):
    def test_hook_never_fails_and_strips_output(self):
        store = tempfile.mkdtemp()
        p = json.dumps({"session_id": "s", "tool_name": "Read", "cwd": store,
                        "tool_input": {"file_path": "/x/a.txt"}, "tool_response": "SECRET BODY"}).encode()
        r = subprocess.run([sys.executable, "-I", str(_ECC / "observe_meta.py"), "post"], input=p,
                           env=dict(os.environ, ECC_CLV2_STORE_WIN=store), capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        for f in Path(store).rglob("*.jsonl"):
            self.assertNotIn("SECRET BODY", f.read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
