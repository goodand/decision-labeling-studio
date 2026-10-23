"""Kiwi-based correction detection must beat the regex on these cases, and the resident server must
answer fast with a regex fallback when it is down. One server for the module; always stopped at the end."""
import socket, subprocess, sys, time, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "ecc-clv2"))
import capture_correction as cc  # noqa: E402
import kiwi_server  # noqa: E402

YES = ["그게 아니라 원본 코드를 import 해야지", "결과서는 정답 전용이잖아, 입력 규칙에 섞지 마",
       "그렇게 하지 않는 게 좋겠어", "스크립트 새로 쓰지 말고 재사용해", "그건 틀린 접근이야", "그렇게 하면 안 돼"]
NO = ["왜 그런지 설명해줘", "진행해", "이건 B 방식으로 가자", "어떤 directory가 더 적절할지 찾아봐", "아니오 결과 파일 보여줘"]


def port_open() -> bool:
    try:
        socket.create_connection((kiwi_server.HOST, kiwi_server.PORT), timeout=0.2).close()
        return True
    except OSError:
        return False


def wait_port(state: bool, seconds=15):
    for _ in range(int(seconds / 0.1)):
        if port_open() == state:
            return True
        time.sleep(0.1)
    return False


def start_server():
    subprocess.Popen([sys.executable, "-X", "utf8", "-I", str(Path(kiwi_server.__file__))],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert wait_port(True), "kiwi server did not come up"


def setUpModule():
    if not port_open():
        start_server()


def tearDownModule():
    wait_port(True, 10)  # a lazily respawned server may still be binding
    kiwi_server.stop()
    wait_port(False)


class Detect(unittest.TestCase):
    def test_kiwi_cases(self):
        for t in YES:
            self.assertTrue(cc.is_correction_kiwi(t), t)
        for t in NO:
            self.assertFalse(cc.is_correction_kiwi(t), t)


class RegexFallback(unittest.TestCase):
    def test_regex_covers_same_cases(self):  # used while the resident server is down/restarting
        for t in YES:
            self.assertTrue(cc.is_correction_regex(t), t)
        for t in NO:
            self.assertFalse(cc.is_correction_regex(t), t)


class Resident(unittest.TestCase):
    def test_server_roundtrip_then_fallback(self):
        t = time.perf_counter()
        self.assertTrue(cc.is_correction("그렇게 하지 않는 게 좋겠어"))
        self.assertLess(time.perf_counter() - t, 0.2)          # served by resident Kiwi, not a fresh load
        self.assertEqual(cc.last_backend, "kiwi")
        self.assertTrue(kiwi_server.stop())
        self.assertTrue(wait_port(False))
        self.assertTrue(cc.is_correction("그게 아니라 원본 코드를 import 해야지"))
        self.assertEqual(cc.last_backend, "regex")              # fallback when the server is down
        self.assertTrue(wait_port(True))                        # ...and the fallback lazily restarts it

    def test_hook_as_installed_uses_kiwi(self):
        """Run the hook exactly as settings.json does (python -I script.py): -I drops the script dir from
        sys.path, so `import kiwi_server` must still work or the hook silently degrades to regex."""
        import json, os, tempfile
        wait_port(True)
        store = tempfile.mkdtemp()
        env = dict(os.environ, ECC_CLV2_STORE_WIN=store)
        p = json.dumps({"session_id": "hk", "cwd": "X:" + chr(92) + "none", "prompt": "그렇게 하지 않는 게 좋겠어"},
                       ensure_ascii=False).encode("utf-8")
        subprocess.run([sys.executable, "-X", "utf8", "-I", cc.__file__], input=p, env=env, timeout=30)
        self.assertTrue((Path(store) / "corrections.jsonl").exists())  # regex alone misses "하지 않는"

    def test_duplicate_start_does_not_double_bind(self):
        wait_port(True)
        p = subprocess.run([sys.executable, "-X", "utf8", "-I", str(Path(kiwi_server.__file__))],
                           capture_output=True, timeout=30)
        self.assertNotEqual(p.returncode, 0)                   # EADDRINUSE: exactly one server lives


if __name__ == "__main__":
    unittest.main()
