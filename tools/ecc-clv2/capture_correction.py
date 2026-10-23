"""UserPromptSubmit hook: record user *corrections* (rule-based) as learning evidence.

ECC's observe hook sees only tool calls, so the lessons the user keeps re-stating
(corrections) never reach the learner. This stores a bounded excerpt (<= MAX_CHARS)
of prompts that match correction markers, per project, next to observations.jsonl.
Never blocks the prompt (always exit 0).
"""
import json, os, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # hooks run with `python -I`: script dir not on path
import platform_compat as pc  # noqa: E402
STORE = pc.store_dir()
MAX_CHARS = 300
AUTOMATED_MARK = "[ECC-AUTOMATED]"  # learner/judge prompts carry this; never treat them as user input
MARKERS = re.compile(
    r"(아니라|아니고|아니야|말고|하지\s*마|하지마|마라|해야지|해야\s*해|해야\s*한다|잖아|틀렸|틀린|잘못|다시\s*해|"
    r"지\s*않|안\s*(돼|되|된다)|못\s|재사용|덮어쓰|원본|정답\s*전용|섞지)")  # mirrors the Kiwi rule; "왜" dropped (questions)
DOC_REF = re.compile(r"[^\s\"']*\.(pdf|hwpx?|xlsx?|xlsm|docx?|pptx?|csv)\b", re.I)


# Rule D (STUDIO-ECC-012): a correction is asserted, not asked, and not hypothetical. Per sentence:
# a sentence ending in "?" is a question; negation inside an if-clause ("작동 안 하면 …") is a
# condition, so only what follows the last 면/으면 counts. Domain rule words still match anywhere.
_SENT = re.compile(r"[^.?!\n]+[.?!]*")
_COND_RE = re.compile(r"^.*(?:으면|면)(?=\s)", re.S)


def _asserted_parts_text(text: str):
    for s in _SENT.findall(text):
        s = s.strip()
        if s and not s.endswith("?"):
            yield _COND_RE.sub("", s)


def is_correction_regex(text: str) -> bool:
    if not text:
        return False
    if DOMAIN_RE.search(text):
        return True
    return any(MARKERS.search(part) for part in _asserted_parts_text(text))


# Morphological rule (Kiwi tags): negation / prohibition / obligation / "-잖아" reproach, or a
# domain rule word. Pure rules on tags, no model judgement.
NEG_FORMS = {("아니", "VCN"), ("않", "VX"), ("말", "VX"), ("못", "MAG"), ("안", "MAG")}
END_FORMS = {"잖아", "잖아요", "어야지", "아야지", "어야", "아야", "어야지요"}
RULE_WORDS = {"틀리", "잘못"}  # lemmas (틀리다 → 틀리/VV)
DOMAIN_RE = re.compile(r"재사용|원본|덮어쓰|정답\s*전용|섞지")  # lexical project rule words (Kiwi splits 재/사용)
last_backend = "regex"


def _tokens_from_server(text: str, timeout=0.5):
    import socket, kiwi_server
    with socket.create_connection((kiwi_server.HOST, kiwi_server.PORT), timeout=timeout) as s:
        s.sendall(json.dumps({"op": "tokens", "text": text}, ensure_ascii=False).encode("utf-8") + b"\n")
        return json.loads(s.makefile("rb").readline().decode("utf-8"))["tokens"]


def _asserted_parts_tokens(tokens):
    """Split Kiwi tokens into sentences at SF; drop questions; keep only what follows the last
    connective 면/으면 (EC) in each sentence."""
    sent = []
    for f, t in list(tokens) + [(".", "SF")]:
        sent.append((f, t))
        if t == "SF":
            if f != "?":
                cut = max((i for i, (g, u) in enumerate(sent) if u == "EC" and g in ("면", "으면")), default=-1)
                yield sent[cut + 1:]
            sent = []


def is_correction_tokens(tokens, text: str = "") -> bool:
    if DOMAIN_RE.search(text):
        return True
    return any(_rule_hit(part) for part in _asserted_parts_tokens(tokens))


def _rule_hit(tokens) -> bool:
    forms = [(f, t) for f, t in tokens]
    if any(ft in NEG_FORMS for ft in forms):  # a bare "아니오/아니요" answer is IC, not VCN, so it never matches
        return True
    return any(f in END_FORMS for f, t in forms if t.startswith("E")) or \
        any(f.startswith(tuple(RULE_WORDS)) for f, t in forms if t.startswith(("N", "V", "XR")))


def is_correction_kiwi(text: str) -> bool:
    return is_correction_tokens(_tokens_from_server(text), text)


def is_correction(text: str) -> bool:
    """Kiwi via resident server when up; regex fallback (and lazy server start) otherwise."""
    global last_backend
    if not text:
        return False
    try:
        r = is_correction_kiwi(text)
        last_backend = "kiwi"
        return r
    except Exception:
        last_backend = "regex"
        _start_server_detached()
        return is_correction_regex(text)


START_TASK = os.environ.get("ECC_KIWI_START_TASK", "ECC_KiwiStart")


import tempfile  # noqa: E402
SPAWN_MARK = Path(tempfile.gettempdir()) / "ecc-clv2-kiwi-spawn.mark"
SPAWN_WINDOW_S = 30  # one start attempt per window, across processes: a booting server takes seconds
_spawned_here = False


def _start_server_detached():
    """Task Scheduler (Windows) / launchd (macOS) job named START_TASK, else a detached child (tests).
    At most one attempt per SPAWN_WINDOW_S, or every call while the server boots starts another one."""
    global _spawned_here
    window = SPAWN_MARK.with_name(f"{SPAWN_MARK.name}.{int(time.time() // SPAWN_WINDOW_S)}")
    try:  # O_EXCL: exactly one process wins each window, whatever the clock or old marks say
        os.close(os.open(window, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    except FileExistsError:
        return
    except OSError:  # cannot write a mark at all: still try, but once per process
        if _spawned_here:
            return
    _spawned_here = True
    pc.start_detached([sys.executable, "-X", "utf8", "-I", str(Path(__file__).with_name("kiwi_server.py"))], START_TASK)


# Credential shapes in free text (the user's own words cannot be allow-listed without losing them).
SECRET_TOKEN = re.compile(r"(?<![\w])(?:AKIA[0-9A-Z]{16}|sk[_-][0-9A-Za-z_-]{16,}|gh[pousr]_[0-9A-Za-z]{30,}"
                          r"|xox[abprs]-[0-9A-Za-z-]{10,}|AIza[0-9A-Za-z_-]{30,}|eyJ[0-9A-Za-z_.-]{20,}"
                          r"|(?=(?:[0-9A-Za-z_-]*\d){2})(?=(?:[0-9A-Za-z_-]*[A-Za-z]){2})[0-9A-Za-z_-]{20,})(?![\w])")
URL_CRED = re.compile(r"(://)[^/\s@]+@")


def mask_secrets(text: str) -> str:
    return SECRET_TOKEN.sub("[비밀]", URL_CRED.sub(r"\1[비밀]@", text))


def make_record(session: str, cwd: str, text: str) -> dict:
    text = mask_secrets(DOC_REF.sub("[문서파일]", " ".join(text.split())))[:MAX_CHARS]
    return {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": "user_correction",
            "session": session, "cwd": cwd, "text": text}


def project_dir(cwd: str) -> Path:
    """Reuse ECC's registry: match the longest registered root that contains cwd."""
    try:
        reg = json.loads((STORE / "projects.json").read_text("utf-8"))
    except (OSError, ValueError):
        return STORE
    c = cwd.replace("\\", "/").lower()
    best = max((v for v in reg.values() if c.startswith(v["root"].replace("\\", "/").lower())),
               key=lambda v: len(v["root"]), default=None)
    return STORE / "projects" / best["id"] if best else STORE


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        text = data.get("prompt", "")
        # Skip automated claude -p sessions (judge/learner set ECC_SKIP_OBSERVE=1) and subagents.
        # (env is not reliably inherited by hooks; automated runs also pass --settings disableAllHooks)
        if (os.environ.get("ECC_SKIP_OBSERVE") == "1" or data.get("agent_id") or text.lstrip().startswith("<")
                or AUTOMATED_MARK in text or not is_correction(text)):
            return 0
        pdir = project_dir(data.get("cwd", ""))
        pdir.mkdir(parents=True, exist_ok=True)
        with open(pdir / "corrections.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(make_record(data.get("session_id", ""), data.get("cwd", ""), text), ensure_ascii=False) + "\n")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
