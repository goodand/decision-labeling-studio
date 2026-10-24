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
        self.assertEqual([v["name"] for v in vals], ["일관성", "최고 수준", "전체 시간"])   # 차이 명확화 removed (STUDIO-ECC-032)
        self.assertEqual({v["side"] for v in vals[:2]}, {"effect"})
        self.assertEqual(vals[2]["side"], "input")

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


class CriteriaOfExcellence(unittest.TestCase):
    """User 2026-10-24: the criteria for 'excellent' come from human decisions, expressed in apt natural language and
    mapped to cases; so supporting human decisions is subordinate to 최고 수준 as well."""
    def test_criteria_chain_is_approved(self):
        g = concepts.load(concepts.DEFAULT_PATH)                          # approved only
        self.assertIn("최고 수준", g.purposes("사람의 의사결정 지원"))
        self.assertIn("검증 비용 절감", g.purposes("사람의 의사결정 지원"))
        self.assertIn("최고 수준", g.purposes("우수한 것의 기준"))
        deps = g.out["depends_on"]
        self.assertEqual(deps["우수한 것의 기준"], {"사람의 결정", "자연어 표현", "사례 매핑"})
        self.assertIn("우수한 것의 기준", deps["우수한 것 선택"])

    def test_decision_records_implement_the_chain(self):
        """decisions/*.json carry the human's words (user_quote), the decision in natural language, and evidence."""
        c = json.loads(concepts.DEFAULT_PATH.read_text("utf-8"))["concepts"]
        self.assertIn("decisions/", c["사람의 결정"].get("artifact", ""))


class UserCorrections20261024(unittest.TestCase):
    def test_pros_cons_and_visualization_links(self):
        """User: 장단점 설명 is for 사람의 의사결정 지원; 시각화 is for 사람의 의사결정 지원 or for 최고 수준 (context)."""
        g = concepts.load(concepts.DEFAULT_PATH)                          # approved only
        self.assertIn("사람의 의사결정 지원", g.out["means_of"]["장단점 설명"])
        self.assertEqual(g.out["means_of"]["시각화"], {"사람의 의사결정 지원", "최고 수준"})
        rels = json.loads(concepts.DEFAULT_PATH.read_text("utf-8"))["relations"]
        rejected = {(r["from"], r["to"]) for r in rels if r["status"] == "rejected"}
        self.assertIn(("장단점 설명", "차이 명확화"), rejected)
        self.assertIn(("시각화", "차이 명확화"), rejected)


class RuleFirstIsForVerification(unittest.TestCase):
    def test_rule_first_serves_verification_not_consistency(self):
        """User: '규칙 먼저, 의미는 마지막' is for efficient verification."""
        g = concepts.load(concepts.DEFAULT_PATH)
        self.assertEqual(g.out["means_of"]["규칙 먼저, 의미는 마지막"], {"검증 비용 절감"})
        self.assertIn("전체 시간", g.purposes("규칙 먼저, 의미는 마지막"))
        rels = json.loads(concepts.DEFAULT_PATH.read_text("utf-8"))["relations"]
        self.assertIn(("규칙 먼저, 의미는 마지막", "일관성"), {(r["from"], r["to"]) for r in rels if r["status"] == "rejected"})


class ExcellenceSelection(unittest.TestCase):
    def test_choosing_the_best_serves_top_quality(self):
        """User: '최고 수준'을 위해서 '우수한 것 선택'이 맞다."""
        g = concepts.load(concepts.DEFAULT_PATH)
        self.assertIn("최고 수준", g.out["means_of"]["우수한 것 선택"])


class ConsistencyByFixing(unittest.TestCase):
    def test_fixing_and_control_serves_consistency(self):
        """User: '고정과 통제'도 '일관성'을 위한 것이 맞다."""
        g = concepts.load(concepts.DEFAULT_PATH)
        self.assertIn("일관성", g.out["means_of"]["고정과 통제"])
        self.assertEqual(g.values_served("고정과 통제", concepts.core_values(concepts.DEFAULT_PATH))[0], "일관성")


class DifferenceClarityRemoved(unittest.TestCase):
    def test_difference_clarity_is_no_longer_a_core_value(self):
        """User 2026-10-24: '핵심 가치'에서 '차이 명확화'를 제외."""
        d = json.loads(concepts.DEFAULT_PATH.read_text("utf-8"))
        self.assertNotIn("차이 명확화", [v["name"] for v in concepts.core_values(concepts.DEFAULT_PATH)])
        self.assertEqual(d["concepts"]["차이 명확화"]["kind"], "means")                   # now a means (STUDIO-ECC-033)


class DecisionSupportForHumanAndAgent(unittest.TestCase):
    def test_difference_clarity_serves_decisions_of_humans_and_agents(self):
        """User: '차이 명확화'도 '의사결정'을 위해서 사용될 때가 많고, Human뿐 아니라 Agent도 마찬가지."""
        g = concepts.load(concepts.DEFAULT_PATH)
        self.assertIn("의사결정 지원", g.out["means_of"]["차이 명확화"])
        self.assertIn("의사결정 지원", g.ancestors("사람의 의사결정 지원"))
        self.assertIn("의사결정 지원", g.ancestors("에이전트의 의사결정 지원"))


if __name__ == "__main__":
    unittest.main()
