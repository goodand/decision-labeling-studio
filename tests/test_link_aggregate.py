"""사업 전체 판정 계산 규칙(설정 파일 aggregate_rules) 회귀 + 구획 단위 저장. Author: Claude."""
import hashlib
import importlib.util
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('link_server', ROOT / 'link_server.py')
ls = importlib.util.module_from_spec(spec); spec.loader.exec_module(ls)
RULES = json.loads((ROOT / 'adapters' / 'program_link' / 'config.example.json').read_text(encoding='utf-8'))['aggregate_rules']


def agg(*labels, n=None):
    n = len(labels) if n is None else n
    return ls.aggregate({f'S{i}': x for i, x in enumerate(labels)}, [f'S{i}' for i in range(n)], RULES)


class RuleTable(unittest.TestCase):
    def test_r1_all_match(self): self.assertEqual(agg('일치', '일치')[:2], ('일치', 'R1'))
    def test_r2_match_plus_undecidable(self):
        r = agg('일치', '판단불가', '일치'); self.assertEqual(r[:2], ('부분일치', 'R2')); self.assertEqual(r[2]['판단불가_구획'], ['S1'])
    def test_r3_match_or_partial_with_mismatch(self):
        self.assertEqual(agg('일치', '불일치')[:2], ('부분일치', 'R3'))
        self.assertEqual(agg('부분일치', '불일치')[:2], ('부분일치', 'R3'))
        self.assertEqual(agg('부분일치', '부분일치')[:2], ('부분일치', 'R3'))
    def test_r4_all_mismatch(self): self.assertEqual(agg('불일치', '불일치')[:2], ('불일치', 'R4'))
    def test_r5_undecidable(self):
        self.assertEqual(agg('판단불가')[:2], ('판단불가', 'R5'))
        self.assertEqual(agg('판단불가', '불일치')[:2], ('판단불가', 'R5'))
    def test_incomplete(self): self.assertEqual(agg('일치', n=2)[:2], (None, 'incomplete'))
    def test_undefined_combinations(self):
        self.assertEqual(agg('부분일치', '판단불가')[:2], (None, 'undefined'))
        self.assertEqual(agg('일치', '판단불가', '불일치')[:2], (None, 'undefined'))


class SegmentVotes(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); self.d = Path(t.name)
        seg = lambda i, lvl: {'id': f'B01-S0{i}', '사업_id': 7, '레벨명': lvl, '사업명': 'x', '회계연도': 2026, 'merged_구조_ids': [10 + i, 20 + i]}
        data = {'kind': 'program_link', 'question': 'q', 'choices': {k: k for k in ['일치', '부분일치', '불일치', '판단불가']},
                'note_required_for': ['부분일치', '판단불가'], 'aggregate_rules': RULES, 'docs': {},
                'businesses': [{'id': 'B01', 'search_name': 'x', 'mentions': [], 'segments': [seg(1, '세부사업'), seg(2, '내역사업')]}]}
        self.dataset = self.d / 'dataset.json'; self.dataset.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        self.votes = self.d / 'votes.json'
        self.http = ls.make_server(self.dataset, self.votes, None, 0, opener=lambda p: None)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.addCleanup(self.http.server_close); self.addCleanup(self.http.shutdown)
        self.url = f'http://127.0.0.1:{self.http.server_port}'

    def post(self, data):
        r = urllib.request.Request(self.url + '/api/votes', data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(r) as resp: return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e: return e.code, json.loads(e.read())

    def test_business_level_input_rejected(self):
        self.assertEqual(self.post({'business_id': 'B01', 'segment_id': None, 'choice': '일치'})[0], 400)

    def get(self, path):
        with urllib.request.urlopen(self.url + path) as resp: return json.loads(resp.read())

    def test_votes_format_unchanged_and_derived_display_only(self):
        self.assertEqual(self.post({'business_id': 'B01', 'segment_id': 'B01-S01', 'choice': '일치'})[0], 200)
        saved = json.loads(self.votes.read_text(encoding='utf-8'))
        self.assertEqual(set(saved), {'schema', 'input_sha256', 'decisions', 'votes'})  # derived 등 새 키 없음
        self.assertEqual(set(saved['votes']['B01/B01-S01']), {'business_id', 'segment_id', 'choice', 'note', 'decided_by', 'submitted_via', 'saved_at', 'dataset_sha256'})
        self.assertEqual(self.get('/api/derived')['B01']['status'], 'incomplete')
        self.post({'business_id': 'B01', 'segment_id': 'B01-S02', 'choice': '불일치'})
        d = self.get('/api/derived')['B01']
        self.assertEqual((d['result'], d['rule'], d['rules_version']), ('부분일치', 'R3', RULES['version']))
        self.assertNotIn('B01', json.loads(self.votes.read_text(encoding='utf-8'))['votes'])

if __name__ == '__main__': unittest.main()
