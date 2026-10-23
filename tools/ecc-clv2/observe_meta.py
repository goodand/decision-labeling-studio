"""Metadata-only front end for ECC continuous-learning-v2 observe.sh.

Strips tool outputs and content-bearing inputs (document text from PDF/Excel/HWP/HWPX
reads, file contents, prompts) before the hook payload reaches observe.sh, and forces
the observer (which would send observations to the Claude API) off.
Usage (Claude Code hook): python observe_meta.py pre|post
"""
import json, msvcrt, os, re, subprocess, sys, time
from pathlib import Path

GIT_BASH = os.environ.get("ECC_GIT_BASH", r"C:\Program Files\Git\bin\bash.exe")
_HERE = Path(__file__).resolve().parent
OBSERVE = Path(os.environ.get("ECC_CLV2_SKILL_DIR") or next(
    (d for d in (_HERE / "continuous-learning-v2", _HERE / "upstream" / "continuous-learning-v2") if d.exists()),
    _HERE / "continuous-learning-v2")) / "hooks" / "observe.sh"
KEEP_INPUT_KEYS = ("file_path", "path", "pattern", "glob", "notebook_path", "url", "subagent_type", "description")
CMD_LIMIT = 200


def posix(p: Path) -> str:
    s = str(p).replace("\\", "/")
    return "/" + s[0].lower() + s[2:]


def sanitize(data: dict) -> dict:
    tool_input = data.get("tool_input") or {}
    safe = {}
    if isinstance(tool_input, dict):
        safe = {k: tool_input[k] for k in KEEP_INPUT_KEYS if isinstance(tool_input.get(k), str)}
        if isinstance(tool_input.get("command"), str):
            safe["command"] = tool_input["command"][:CMD_LIMIT]
    out = {k: data[k] for k in ("session_id", "tool_name", "tool_use_id", "cwd", "agent_id") if k in data}
    out["tool_input"] = safe
    out["tool_response"] = ""  # never persist tool output
    return out


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else "post"
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except Exception:
        return 0
    env = dict(os.environ, CLAUDE_CODE_ENTRYPOINT=os.environ.get("CLAUDE_CODE_ENTRYPOINT", "cli"))
    env.pop("ECC_OBSERVER_ALLOW_WINDOWS", None)
    env.setdefault("CLV2_PYTHON_CMD", "python")
    # Pin the store here. Claude Code rewrites settings.json env paths to "C:/...",
    # which observe.sh rejects as non-absolute and then falls back to ~/.local/share.
    env["CLV2_HOMUNCULUS_DIR"] = os.environ.get("ECC_CLV2_STORE", posix(Path.home() / ".claude" / "ecc-homunculus"))
    store = Path(re.sub(r"^/([a-z])/", r"\1:/", env["CLV2_HOMUNCULUS_DIR"]))
    store.mkdir(parents=True, exist_ok=True)
    with open(store / ".observe.lock", "a+b") as guard:  # E5: serialize observe.sh appends (no lock in ECC)
        deadline = time.monotonic() + 25
        while True:
            try:
                msvcrt.locking(guard.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() > deadline:
                    return 0  # drop one observation rather than block the session
                time.sleep(0.05)
        try:
            subprocess.run([GIT_BASH, posix(OBSERVE), phase],
                           input=json.dumps(sanitize(data), ensure_ascii=False).encode("utf-8"),
                           env=env, capture_output=True, timeout=30)
        finally:
            guard.seek(0)
            msvcrt.locking(guard.fileno(), msvcrt.LK_UNLCK, 1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
