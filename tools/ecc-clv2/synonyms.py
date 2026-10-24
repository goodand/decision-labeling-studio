"""Synonym table: meaning decided once per group, then applied by rule (STUDIO-ECC-022).

An LLM may propose a group (status "proposed"); a human approves it ("approved", approved_by "human",
with evidence quotes). Only approved groups map terms to their canonical token (the first term), so
matching stays deterministic and every mapping traces back to a human decision.
"""
import json, unicodedata
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent / "synonyms.json"
STATUSES = {"proposed", "approved", "rejected"}


def _norm(term: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", term).lower().split())


class Table:
    def __init__(self, groups):
        self.groups = groups
        self._canon = {}
        for g in groups:
            if g["status"] == "approved":
                head = _norm(g["terms"][0])
                for t in g["terms"]:
                    self._canon[_norm(t)] = head

    def canon(self, term: str) -> str:
        n = _norm(term)
        return self._canon.get(n, n)

    def terms_of(self, term: str) -> set:
        head = self.canon(term)
        return {t for t, h in self._canon.items() if h == head} or {_norm(term)}


EMPTY = Table([])


def validate(doc) -> list:
    if not isinstance(doc, dict) or doc.get("schema") != "ecc-synonyms/v1" or not isinstance(doc.get("groups"), list):
        raise ValueError("not an ecc-synonyms/v1 document")
    ids, owner = set(), {}
    for g in doc["groups"]:
        gid = g.get("id")
        if not gid or gid in ids:
            raise ValueError(f"missing or duplicate id: {gid!r}")
        ids.add(gid)
        if g.get("status") not in STATUSES:
            raise ValueError(f"{gid}: unknown status {g.get('status')!r}")
        terms = g.get("terms")
        if not isinstance(terms, list) or len({_norm(t) for t in terms if isinstance(t, str)}) < 2:
            raise ValueError(f"{gid}: a group needs at least two distinct terms")
        if g["status"] == "approved":
            if g.get("approved_by") != "human":
                raise ValueError(f"{gid}: only a human approves (approved_by must be 'human')")
            if not g.get("evidence"):
                raise ValueError(f"{gid}: an approved group needs evidence quotes")
            for t in terms:
                n = _norm(t)
                if n in owner:
                    raise ValueError(f"{gid}: term {t!r} is already in approved group {owner[n]}")
                owner[n] = gid
    return doc["groups"]


def load(path=DEFAULT_PATH) -> Table:
    p = Path(path)
    if not p.exists():
        return EMPTY
    return Table(validate(json.loads(p.read_text("utf-8"))))
