"""Concept relations (STUDIO-ECC-025): is_a / means_of / depends_on / responsibility among the user's working
principles. An LLM proposes, a human approves; the file is validated by rule."""
import json, sys, tempfile, unittest
from pathlib import Path

_ECC = Path(__file__).resolve().parents[1] / "tools" / "ecc-clv2"
sys.path.insert(0, str(_ECC))
import concepts  # noqa: E402


def doc(rels, cons=None):
    p = Path(tempfile.mkdtemp()) / "c.json"
    p.write_text(json.dumps({"schema": "ecc-concepts/v1", "concepts": cons or {"A": {}, "B": {}, "C": {}}, "relations": rels},
                            ensure_ascii=False), "utf-8")
    return p


EV = [{"date": "2026-10-24", "quote": "q"}]


class Validate(unittest.TestCase):
    def test_shipped_file_is_valid_and_answers_queries(self):
        g = concepts.load(concepts.DEFAULT_PATH, include_proposed=True)
        self.assertIn("결정론적", g.ancestors("규칙 기반"))
        self.assertIn("검증 비용 절감", g.purposes("TDD"))
        self.assertIn("사람의 의사결정 지원", g.purposes("TDD"))          # transitive: TDD -> 검증 비용 절감 -> 지원

    def test_only_approved_by_default(self):
        g = concepts.load(doc([{"type": "is_a", "from": "A", "to": "B", "status": "proposed", "evidence": EV}]))
        self.assertEqual(g.ancestors("A"), set())

    def test_rejects_bad_files(self):
        bad = [[{"type": "kind_of", "from": "A", "to": "B", "status": "proposed", "evidence": EV}],         # unknown type
               [{"type": "is_a", "from": "A", "to": "Z", "status": "proposed", "evidence": EV}],            # undeclared concept
               [{"type": "is_a", "from": "A", "to": "B", "status": "approved", "evidence": EV}],            # approved w/o human
               [{"type": "is_a", "from": "A", "to": "B", "status": "approved", "approved_by": "human", "evidence": []}],
               [{"type": "is_a", "from": "A", "to": "B", "status": "proposed", "evidence": EV},
                {"type": "is_a", "from": "B", "to": "A", "status": "proposed", "evidence": EV}]]            # is_a cycle
        for rels in bad:
            with self.assertRaises(ValueError, msg=rels):
                concepts.load(doc(rels), include_proposed=True)


if __name__ == "__main__":
    unittest.main()
