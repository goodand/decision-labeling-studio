"""결정 템플릿: 모든 kind가 같은 칸을 채우고, 기존 서버의 선택지와 어긋나지 않는지."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = json.loads((ROOT / 'templates' / 'decision_template.json').read_text(encoding='utf-8'))['kwargs']
KINDS = {p.stem: json.loads(p.read_text(encoding='utf-8')) for p in (ROOT / 'templates' / 'kinds').glob('*.json')}


class DecisionTemplateTests(unittest.TestCase):
    def test_template_uses_only_declared_slots(self):
        used = set(re.findall(r'\{(\w+)\}', BASE['template']))
        self.assertEqual(used, set(BASE['input_variables']) | set(BASE['partial_variables']))

    def test_every_kind_fills_every_slot(self):
        for kind, v in KINDS.items():
            with self.subTest(kind=kind):
                self.assertTrue(set(BASE['input_variables']) <= set(v))
                self.assertTrue(v['observe'] and v['selector'] and v['action'])

    def test_capture_and_record_match_studio_server(self):
        src = (ROOT / 'studio_server.py').read_text(encoding='utf-8')
        cap, rec = [re.findall(r"'([^']+)'", g) for g in re.search(r"allowed=\(([^)]*)\) if capture else \(([^)]*)\)", src).groups()]
        self.assertEqual(KINDS['capture']['action'], cap)
        self.assertEqual(KINDS['record']['action'], rec)


if __name__ == '__main__':
    unittest.main()
