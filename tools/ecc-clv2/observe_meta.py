"""Metadata-only front end for ECC continuous-learning-v2 observe.sh.

Strips tool outputs and content-bearing inputs (document text from PDF/Excel/HWP/HWPX
reads, file contents, prompts) before the hook payload reaches observe.sh, and forces
the observer (which would send observations to the Claude API) off.
Usage (Claude Code hook): python observe_meta.py pre|post
"""
import json, os, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # hooks run with `python -I`: script dir not on path
import platform_compat as pc  # noqa: E402

GIT_BASH = pc.bash_path()
_HERE = Path(__file__).resolve().parent
OBSERVE = Path(os.environ.get("ECC_CLV2_SKILL_DIR") or next(
    (d for d in (_HERE / "continuous-learning-v2", _HERE / "upstream" / "continuous-learning-v2") if d.exists()),
    _HERE / "continuous-learning-v2")) / "hooks" / "observe.sh"
KEEP_INPUT_KEYS = ("file_path", "path", "pattern", "glob", "notebook_path", "url", "subagent_type", "description")
CMD_LIMIT = 200
# A command's first line only, and nothing after an inline-script flag: those bodies are content.
_INLINE = re.compile(r"(\s-(?:c|e|E|exec)\s)|(<<)")
# Credentials that can sit on the first line: user:pass@ in URLs, and KEY=value for secret-like keys.
_URL_CRED = re.compile(r"(://[^/\s:@]+:)[^@\s]+(@)")
_ENV_CRED = re.compile(r"((?:^|\s)(?:[A-Z0-9_]*(?:PASS(?:WORD)?|SECRET|TOKEN|KEY|AUTH)[A-Z0-9_]*)=)(\S+)")


def safe_command(cmd: str) -> str:
    line = cmd.splitlines()[0] if cmd.splitlines() else ""
    m = _INLINE.search(line)
    if m:
        line = line[: m.end()] + "[…]"
    line = _URL_CRED.sub(r"\1[REDACTED]\2", line)
    line = _ENV_CRED.sub(r"\1[REDACTED]", line)
    return line[:CMD_LIMIT]


def sanitize(data: dict) -> dict:
    tool_input = data.get("tool_input") or {}
    safe = {}
    if isinstance(tool_input, dict):
        safe = {k: tool_input[k][:CMD_LIMIT] for k in KEEP_INPUT_KEYS if isinstance(tool_input.get(k), str)}
        if isinstance(tool_input.get("command"), str):  # first line only: heredoc/inline-script bodies are content
            safe["command"] = safe_command(tool_input["command"])
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
    store = pc.store_dir()
    env["CLV2_HOMUNCULUS_DIR"] = pc.to_bash_path(store)
    store.mkdir(parents=True, exist_ok=True)
    with open(store / ".observe.lock", "a+b") as guard, pc.file_lock(guard, 25) as held:  # E5: serialize observe.sh appends (no lock in ECC)
        if not held:
            return 0  # drop one observation rather than block the session
        subprocess.run([GIT_BASH, pc.to_bash_path(OBSERVE), phase],
                       input=json.dumps(sanitize(data), ensure_ascii=False).encode("utf-8"),
                       env=env, capture_output=True, timeout=30)
    return 0


if __name__ == "__main__":
    sys.exit(main())
