"""Concept relations among working principles (STUDIO-ECC-025): proposed by an LLM, approved by a human,
queried by rule. Types: is_a (하위→상위개념), means_of (수단→목적), depends_on, responsibility."""
import json
from collections import defaultdict
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent / "concepts.json"
TYPES = {"is_a", "means_of", "depends_on", "responsibility"}
STATUSES = {"proposed", "approved", "rejected"}


class Graph:
    def __init__(self, rels):
        self.out = defaultdict(lambda: defaultdict(set))
        for r in rels:
            self.out[r["type"]][r["from"]].add(r["to"])

    def _reach(self, kinds, start):
        seen, stack = set(), [start]
        while stack:
            node = stack.pop()
            for k in kinds:
                for n in self.out[k].get(node, ()):
                    if n not in seen:
                        seen.add(n)
                        stack.append(n)
        return seen

    def ancestors(self, concept):  # 상위개념, transitive
        return self._reach(("is_a",), concept)

    def purposes(self, concept):  # what this is a means to, transitive (through is_a too)
        return self._reach(("means_of", "is_a"), concept)


def validate(doc) -> list:
    if not isinstance(doc, dict) or doc.get("schema") != "ecc-concepts/v1":
        raise ValueError("not an ecc-concepts/v1 document")
    cons = doc.get("concepts") or {}
    for r in doc.get("relations", []):
        if r.get("type") not in TYPES:
            raise ValueError(f"unknown relation type {r.get('type')!r}")
        if r.get("status") not in STATUSES:
            raise ValueError(f"unknown status {r.get('status')!r}")
        for end in ("from", "to"):
            if r.get(end) not in cons:
                raise ValueError(f"undeclared concept {r.get(end)!r}")
        if r["status"] == "approved" and (r.get("approved_by") != "human" or not r.get("evidence")):
            raise ValueError(f"{r['from']}->{r['to']}: approval needs approved_by 'human' and evidence")
    g = Graph([r for r in doc["relations"] if r["status"] != "rejected" and r["type"] == "is_a"])
    for c in cons:
        if c in g.ancestors(c):
            raise ValueError(f"is_a cycle through {c!r}")
    return doc["relations"]


def load(path=DEFAULT_PATH, include_proposed=False) -> Graph:
    rels = validate(json.loads(Path(path).read_text("utf-8")))
    keep = {"approved", "proposed"} if include_proposed else {"approved"}
    return Graph([r for r in rels if r["status"] in keep])
