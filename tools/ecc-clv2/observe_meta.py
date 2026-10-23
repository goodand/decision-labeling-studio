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
# Allowlist (STUDIO-ECC-019): a command is reduced to its SHAPE. Kept: program names, unquoted
# lowercase subcommand words, flag NAMES, shell separators. Dropped: every quoted token, every value
# (anything after "=", paths, URLs, numbers, mixed case), assignments, and all lines after the first.
# Residual risk, documented: an unquoted all-lowercase secret without digits used as a positional word.
_TOK = re.compile(r"""(?:"[^"]*"|'[^']*'|[^\s"'])+""")
_SEP = {"&&", "||", "|", ";"}
_PROG = re.compile(r"^[a-z][a-z0-9._+-]{0,29}$")       # lower case program names (python3, kubectl, gh)
_FLAG = re.compile(r"^--?[A-Za-z][A-Za-z-]{0,39}$")     # flag NAMES carry no digits
_SHORT_JOINED = re.compile(r"^-[A-Za-z].")              # -pVALUE: keep -p, drop the joined value
_WORD = re.compile(r"^[a-z][a-z_.:-]{0,29}$|^[a-z][a-z0-9]{1,2}$")  # subcommands; digits only in short words (s3, k8s)
_FREE_WORD = re.compile(r"^[A-Za-z][a-z]{0,19}$")       # free text: plain words only (Run, tests, password)
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def safe_command(cmd: str) -> str:
    lines = cmd.splitlines()
    out, expect_prog = [], True
    for tok in _TOK.findall(lines[0] if lines else ""):
        if tok in _SEP:
            out.append(tok)
            expect_prog = True
            continue
        if '"' in tok or "'" in tok:
            continue  # quoted = a value
        if expect_prog:
            if _ASSIGN.match(tok):
                continue  # VAR=value prefix
            name = tok.rstrip("/").rsplit("/", 1)[-1]
            if _PROG.match(name) and sum(ch.isdigit() for ch in name) <= 2:
                out.append(name)
            expect_prog = False
        elif tok.startswith("-"):
            name = tok.split("=", 1)[0]
            if not name.startswith("--") and _SHORT_JOINED.match(name) and not _FLAG.match(name):
                name = name[:2]
            if _FLAG.match(name):
                out.append(name)
        elif _WORD.match(tok):
            out.append(tok)
    return " ".join(out)[:CMD_LIMIT]


def safe_url(url: str) -> str:
    """scheme://host only: paths and query strings carry tokens and signatures."""
    from urllib.parse import urlsplit
    try:
        u = urlsplit(url.strip())
    except ValueError:
        return ""
    host = (u.hostname or "").lower()
    return f"{u.scheme.lower()}://{host}" if u.scheme in ("http", "https") and host else ""


def safe_text(text: str) -> str:
    """Free text (description, pattern): plain words only; any token with digits, symbols or mixed case goes."""
    return " ".join(w for w in re.split(r"[^\w]+", text) if _FREE_WORD.match(w))[:CMD_LIMIT]


SHAPE = {"url": safe_url, "description": safe_text, "pattern": safe_text}


def sanitize(data: dict) -> dict:
    tool_input = data.get("tool_input") or {}
    safe = {}
    if isinstance(tool_input, dict):
        safe = {k: SHAPE.get(k, lambda v: v[:CMD_LIMIT])(tool_input[k]) for k in KEEP_INPUT_KEYS
                if isinstance(tool_input.get(k), str)}
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
