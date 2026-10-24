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
        self.assertIn("전체 시간", g.purposes("TDD"))                     # transitive up to the input value

    def test_user_stated_hierarchy_is_approved(self):
        """User 2026-10-24: 의사결정 지원 is a means of 검증 비용 절감 (not the reverse); core values rank effect > input."""
        g = concepts.load(concepts.DEFAULT_PATH)                          # approved only
        self.assertIn("검증 비용 절감", g.purposes("사람의 의사결정 지원"))
        self.assertNotIn("사람의 의사결정 지원", g.purposes("검증 비용 절감"))
        self.assertIn("전체 시간", g.purposes("검증 비용 절감"))
        vals = concepts.core_values(concepts.DEFAULT_PATH)
        self.assertEqual([v["name"] for v in vals], ["일관성", "최고 수준", "차이 명확화", "전체 시간"])
        self.assertEqual({v["side"] for v in vals[:3]}, {"effect"})
        self.assertEqual(vals[3]["side"], "input")

    def test_values_served_by_a_concept_are_ranked(self):
        g = concepts.load(concepts.DEFAULT_PATH, include_proposed=True)
        served = g.values_served("고정과 통제", concepts.core_values(concepts.DEFAULT_PATH))
        self.assertEqual(served[0], "일관성")                              # effect values rank above the input value

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
