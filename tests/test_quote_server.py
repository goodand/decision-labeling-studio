"""차별점 인용 검수 API 회귀: 원본 sha 결합, 인용 단위 판정 규칙, 형식 불변. Author: Claude."""
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
spec = importlib.util.spec_from_file_location('quote_server', ROOT / 'quote_server.py')
cs = importlib.util.module_from_spec(spec); spec.loader.exec_module(cs)


class ConflictTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); self.d = Path(t.name)
        self.src = self.d / 'doc.hwp'; self.src.write_bytes(b'fake hwp bytes')
        sha = hashlib.sha256(self.src.read_bytes()).hexdigest()
        cases = [{'pair_id': 'P1', 'new_business': 'A', 'comparison_business': 'B',
                  'evidence': {'quote': 'q', 'sources': [{'path': str(self.src), 'sha256': sha}]},
                  'audit_cards': [{'id': 'q1', 'title': 't', 'quote': 'q', 'location': ''}, {'id': 'q2', 'title': 't2', 'quote': 'q2', 'location': ''}]},
                 {'pair_id': 'P2', 'evidence': {'sources': [{'path': str(self.d / 'none.hwp'), 'sha256': '0' * 64}]}}]
        self.dataset = self.d / 'cases.json'; self.dataset.write_text(json.dumps(cases), encoding='utf-8')
        self.votes = self.d / 'votes.json'
        self.opened = []
        self.http = cs.make_server(self.dataset, self.votes, None, 0, opener=self.opened.append)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.addCleanup(self.http.server_close); self.addCleanup(self.http.shutdown)
        self.url = f'http://127.0.0.1:{self.http.server_port}'

    def req(self, path, data=None, origin=None):
        h = {'Content-Type': 'application/json'}
        if origin: h['Origin'] = origin
        r = urllib.request.Request(self.url + path, data=json.dumps(data).encode() if data is not None else None, headers=h)
        try:
            with urllib.request.urlopen(r) as resp: return resp.status, resp.read()
        except urllib.error.HTTPError as e: return e.code, e.read()

    def vote(self, **kw):
        base = {'pair_id': 'P1', 'quote_id': 'q1', 'choice': '맞음', 'note': ''}
        base.update(kw); return self.req('/api/votes', base)

    def test_source_served_only_when_sha_matches(self):
        self.assertEqual(self.req('/api/source-native?row=P1:0'), (200, b'fake hwp bytes'))
        self.assertEqual(self.req('/api/source-native?row=P2:0')[0], 400)
        self.src.write_bytes(b'changed')
        self.assertEqual(self.req('/api/source-native?row=P1:0')[0], 400)

    def test_per_quote_vote_rules_and_record(self):
        self.assertEqual(self.vote(choice='틀림')[0], 400)                 # 이유 필요
        self.assertEqual(self.vote(choice='판단불가')[0], 400)
        self.assertEqual(self.vote(choice='accurate')[0], 400)             # 옛 선택지 거부
        self.assertEqual(self.vote(quote_id='q9')[0], 400)                 # 없는 인용
        self.assertEqual(self.vote(pair_id='NOPE')[0], 400)
        self.assertEqual(self.vote()[0], 200)
        self.assertEqual(self.vote(quote_id='q2', choice='틀림', note='공통 설명이지 차별점이 아님')[0], 200)
        saved = json.loads(self.votes.read_text(encoding='utf-8'))
        self.assertEqual(saved['schema'], 'studio-votes/v1')
        self.assertEqual(set(saved['votes']), {'P1/q1', 'P1/q2'})       # 쌍이 아니라 인용 단위 키
        rec = saved['votes']['P1/q2']
        self.assertEqual((rec['quote_id'], rec['choice'], rec['decided_by']), ('q2', '틀림', 'human'))
        self.assertEqual(len(rec['source_sha256'][0]), 64)

    def test_foreign_origin_and_unknown_static_rejected(self):
        self.assertEqual(self.req('/api/votes', {}, origin='http://evil.example')[0], 403)
        self.assertEqual(self.req('/quote_server.py')[0], 404)
        self.assertEqual(self.req('/rhwp/rhwp_bg.wasm')[0], 404)  # --rhwp not given

    def test_votes_bound_to_dataset_revision(self):
        self.vote()
        self.dataset.write_text('[{"pair_id":"P1"}]', encoding='utf-8')
        with self.assertRaises(ValueError): cs.make_server(self.dataset, self.votes, None, 0)


    def test_open_source_file_and_directory(self):
        self.assertEqual(self.req('/api/open-source', {'row': 'P1:0', 'target': 'file'})[0], 200)
        self.assertEqual(self.req('/api/open-source', {'row': 'P1:0', 'target': 'directory'})[0], 200)
        self.assertEqual(self.opened, [str(self.src), str(self.src.parent)])
        self.assertEqual(self.req('/api/open-source', {'row': 'P1:0', 'target': 'C:/Windows'})[0], 400)
        self.assertEqual(self.req('/api/open-source', {'row': 'P2:0', 'target': 'file'})[0], 400)  # 파일 없음
        self.assertEqual(self.req('/api/open-source', {'row': 'X:0', 'target': 'file'})[0], 404)
        self.assertEqual(self.req('/api/open-source', {'row': 'P2:0', 'target': 'directory'})[0], 200)  # 파일 없어도 폴더는 대안
        self.src.write_bytes(b'changed')
        self.assertEqual(self.req('/api/open-source', {'row': 'P1:0', 'target': 'file'})[0], 400)  # sha 불일치
        self.assertEqual(self.req('/api/open-source', {'row': 'P1:0', 'target': 'file'}, origin='http://evil.example')[0], 403)
        self.assertEqual(len(self.opened), 3)


if __name__ == '__main__': unittest.main()
