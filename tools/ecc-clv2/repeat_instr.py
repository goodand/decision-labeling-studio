"""Repeated-instruction detector (rule tier, no Kiwi): a phrase the user writes in several DIFFERENT
sessions is a standing instruction the agent keeps forgetting. Repetition across sessions is the
signal; nothing here interprets meaning.

Rules: mask URLs/paths/document names; NFKC + lowercase; split on non-word characters; strip one trailing particle from JOSA when
the word stays >= 2 chars; word n-grams of 1..MAX_N that contain a content word (not in STOP, >= 2 chars); count DISTINCT sessions per n-gram; report
n-grams seen in >= MIN_SESSIONS sessions, dropping a shorter n-gram when a longer one covers the
same session set. Document paths are masked before indexing (capture_correction.DOC_REF).
"""
import json, re, time, unicodedata
from collections import defaultdict

import capture_correction as cc  # reuse the hook's own path mask and size cap

MIN_SESSIONS = 3   # tier-2 tunable: how many sessions make an instruction
MAX_N = 6
MAX_WORDS = 80     # per prompt; long pastes are not instructions
MAX_WORD_LEN = 40
# Credential formats (lower-cased): AWS, Stripe/OpenAI-style, GitHub, Slack, Google, JWT; plus any long
# letter+digit blob. Kept narrow so ordinary words like gpt4turbo2024 or sk_learn survive (round 3).
_KEY_SHAPE = re.compile(r"^(akia[0-9a-z]{16}|sk[_-](?:live|test|proj)?[_-]?[0-9a-z]{16,}|gh[pousr]_[0-9a-z]{30,}"
                        r"|xox[abprs]-[0-9a-z-]{10,}|aiza[0-9a-z_-]{30,}|ya29[0-9a-z_-]{20,}|eyj[0-9a-z_-]{20,}"
                        r"|(?=.*[_-])(?=(?:.*\d){4})(?=(?:.*[a-z]){4})[0-9a-z_-]{16,}"
                        r"|(?=(?:.*\d){4})(?=(?:.*[a-z]){4})[0-9a-z_-]{24,})$")
JOSA = ("에서는", "으로는", "에게", "에서", "으로", "까지", "부터", "처럼", "보다", "이나", "이랑",
        "은", "는", "이", "가", "을", "를", "의", "에", "도", "로", "와", "과", "만", "랑")
_TOKEN = re.compile(r"\[[^\]\s]+\]|\w+", re.UNICODE)   # keeps [url]/[경로]/[문서파일] placeholders whole
_URL = re.compile(r"https?://\S+|www\.\S+", re.I)
_PATH = re.compile(r"(?<![\w])(?:[A-Za-z]:[\\/]|~?/)[^\s\"']*[\\/][^\s\"']*")
# Function words and light verbs (fixed list). A phrase made only of these, or of placeholders, is not an
# instruction (real-run noise 2026-10-24: "할 수", "것 같은데", "수 있어", "그 다음").
STOP = frozenset("""
할 수 것 거 게 걸 때 줄 듯 데 등 및 또 더 좀 잘 다 안 못 왜 뭐 이 그 저 이런 그런 저런 이거 그거 저거 여기 거기
있는 있어 있도록 있게 있지 있습니다 있다 있을 없는 없어 없다 같은데 같아 같은 같이 좋은 좋을 좋아 좋겠어
하는 하고 해서 해줘 해라 한다 했다 했어 하면 하게 해 한 하여 하기 할때 대한 위한 위해 통해 대해 관련 다음 지금
사용 부분 경우 정도 내가 너가 네가 우리 the a an to of in on for and or is are be it this that with as
""".split())


def _content(w: str) -> bool:
    return len(w) >= 2 and w not in STOP and not w.startswith("[")


def words(text: str) -> list:
    t = cc.DOC_REF.sub("[문서파일]", text)
    t = _PATH.sub(" [경로] ", _URL.sub(" [url] ", t))
    t = unicodedata.normalize("NFKC", t).lower()
    out = []
    for w in _TOKEN.findall(t):
        w = w.strip("_")
        if not w:
            continue
        if w.startswith("["):
            out.append(w)
            continue
        for j in JOSA:  # longest first (tuple is ordered that way)
            if w.endswith(j) and len(w) - len(j) >= 2:
                w = w[: -len(j)]
                break
        if len(w) <= MAX_WORD_LEN and not _KEY_SHAPE.match(w):
            out.append(w)  # keys, hashes, pasted blobs are not words of an instruction
    return out[:MAX_WORDS]


class Index:
    def __init__(self):
        self.phrases = defaultdict(set)  # phrase -> {session ids}

    def add(self, session: str, text: str):
        ws = words(text)
        for n in range(1, MAX_N + 1):  # n=1 too: 장단점·시각화 recur with different neighbours
            for i in range(len(ws) - n + 1):
                gram = ws[i:i + n]
                if any(_content(w) for w in gram) and _content(gram[0] if n == 1 else "xx"):
                    self.phrases[" ".join(gram)].add(session)

    def repeated(self, min_sessions: int = MIN_SESSIONS) -> list:
        hits = {p: s for p, s in self.phrases.items() if len(s) >= min_sessions}
        rows = []
        for p, s in hits.items():
            covered = any(q != p and f" {p} " in f" {q} " and hits[q] == s for q in hits)
            if not covered:
                rows.append({"phrase": p, "sessions": len(s)})
        rows.sort(key=lambda r: (-r["sessions"], -len(r["phrase"]), r["phrase"]))
        return rows

    def merge(self, other: "Index"):
        for p, s in other.phrases.items():
            self.phrases[p] |= s

    def to_json(self) -> str:
        return json.dumps({p: sorted(s) for p, s in self.phrases.items()}, ensure_ascii=False)

    @classmethod
    def from_json(cls, s: str) -> "Index":
        idx = cls()
        for p, sess in json.loads(s).items():
            idx.phrases[p] = set(sess)
        return idx


def records(idx: Index, min_sessions: int = MIN_SESSIONS) -> list:
    """Same shape family as user_correction so learn_now can read them in the same file list."""
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return [{"timestamp": now, "event": "user_repeated_instruction", "phrase": r["phrase"][:cc.MAX_CHARS],
             "sessions": r["sessions"], "text": r["phrase"][:cc.MAX_CHARS]} for r in idx.repeated(min_sessions)]
