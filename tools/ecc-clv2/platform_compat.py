"""The only place that branches on the OS (Windows / macOS / Linux) for the ecc-clv2 hooks.

store_dir()       one store for every script (was: env in capture_correction, fixed path elsewhere)
bash_path()       Git Bash on Windows, system bash elsewhere (runs ECC observe.sh)
to_bash_path(p)   C:\\x -> /c/x for Git Bash; unchanged on POSIX
from_bash_path(s) inverse of to_bash_path
file_lock(f, t)   non-blocking exclusive lock with a deadline (msvcrt / fcntl)
start_detached()  wake the resident Kiwi server: Task Scheduler / launchd, else a detached child
"""
import contextlib, os, re, shutil, subprocess, sys, time
from pathlib import Path

IS_WIN = os.name == "nt"
DEFAULT_STORE = Path.home() / ".claude" / "ecc-homunculus"


def from_bash_path(s: str) -> str:
    return re.sub(r"^/([a-zA-Z])/", r"\1:/", s) if IS_WIN else s


def to_bash_path(p) -> str:
    s = str(p)
    if not IS_WIN:
        return s
    s = s.replace("\\", "/")
    return "/" + s[0].lower() + s[2:] if re.match(r"^[a-zA-Z]:/", s) else s


def store_dir() -> Path:
    """ECC_CLV2_STORE_WIN (native path, kept for existing Windows setups) > ECC_CLV2_STORE (may be the
    Git Bash form /c/...) > ~/.claude/ecc-homunculus."""
    v = os.environ.get("ECC_CLV2_STORE_WIN") or os.environ.get("ECC_CLV2_STORE")
    return Path(from_bash_path(v)) if v else DEFAULT_STORE


LEARNER_CONFIG_DEFAULT = Path.home() / ".claude-ecc"


def learner_env(env: dict) -> dict:
    """The learner/judge `claude -p` runs under its own config dir when it exists (ECC_CLAUDE_CONFIG_DIR,
    default ~/.claude-ecc): a separate (e.g. personal) login that never touches the main session's."""
    cfg = Path(os.environ.get("ECC_CLAUDE_CONFIG_DIR") or LEARNER_CONFIG_DEFAULT).expanduser()
    return dict(env, CLAUDE_CONFIG_DIR=str(cfg)) if cfg.is_dir() else env


def bash_path() -> str:
    if os.environ.get("ECC_GIT_BASH"):
        return os.environ["ECC_GIT_BASH"]
    if IS_WIN:
        return r"C:\Program Files\Git\bin\bash.exe"
    return shutil.which("bash") or "/bin/bash"


@contextlib.contextmanager
def file_lock(f, timeout: float):
    """Yield True once the 1-byte lock on f is held, False if the deadline passed (caller skips)."""
    if IS_WIN:
        import msvcrt
        take = lambda: msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)  # noqa: E731
        drop = lambda: (f.seek(0), msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1))  # noqa: E731
    else:
        import fcntl
        take = lambda: fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # noqa: E731
        drop = lambda: fcntl.flock(f.fileno(), fcntl.LOCK_UN)  # noqa: E731
    deadline = time.monotonic() + timeout
    while True:
        try:
            take()
            break
        except OSError:
            if time.monotonic() > deadline:
                yield False
                return
            time.sleep(0.05)
    try:
        yield True
    finally:
        drop()


def _run_service(task: str) -> bool:
    """Ask the OS service manager to start the server, so it outlives the hook process
    (on Windows a hook's children die with its Job Object, cf. ECC #2489)."""
    if IS_WIN:
        cmd = ["schtasks", "/Run", "/TN", task]
    elif sys.platform == "darwin":
        cmd = ["launchctl", "kickstart", f"gui/{os.getuid()}/{task}"]
    else:
        cmd = ["systemctl", "--user", "start", task]
    try:
        return subprocess.run(cmd, capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False


def start_detached(argv, task: str):
    if _run_service(task):
        return
    try:  # no service registered (tests, fresh machine): a detached child
        kw = ({"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP} if IS_WIN
              else {"start_new_session": True})
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True, **kw)
    except Exception:
        pass
