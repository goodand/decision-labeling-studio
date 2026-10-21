"""program_link API regressions: doc sha binding, vote rules, separate vote file. Author: Claude."""
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


class LinkTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); self.d = Path(t.name)
        self.src = self.d / 'a.hwp'; self.src.write_bytes(b'judgment')
        sha = hashlib.sha256(b'judgment').hexdigest()
        data = {'kind': 'program_link', 'question': 'q', 'choices': {'일치': '일치', '부분일치': '부분일치', '불일치': '불일치', '판단불가': '판단불가'},
                'note_required_for': ['부분일치', '판단불가'],
                'docs': {'D1': {'id': 'D1', 'path': str(self.src), 'name': 'a.hwp', 'sha256': sha, 'status': 'ok'},
                         'D2': {'id': 'D2', 'path': str(self.d / 'gone.hwp'), 'name': 'gone.hwp', 'sha256': '0' * 64, 'status': 'missing'}},
                'businesses': [{'id': 'B01', 'search_name': 'x', 'mentions': [], 'segments': [{'id': 'B01-S01'}]},
                               {'id': 'B02', 'search_name': 'y', 'mentions': [], 'segments': [{'id': 'B02-S01'}]}]}
        self.dataset = self.d / 'dataset.json'; self.dataset.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        self.votes = self.d / 'votes.json'; self.opened = []
        self.http = ls.make_server(self.dataset, self.votes, None, 0, opener=self.opened.append)
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

    def test_doc_only_with_matching_sha(self):
        self.assertEqual(self.req('/api/doc?id=D1'), (200, b'judgment'))
        self.assertEqual(self.req('/api/doc?id=D2')[0], 400)
        self.assertEqual(self.req('/api/doc?id=../x')[0], 404)
        self.src.write_bytes(b'changed'); self.assertEqual(self.req('/api/doc?id=D1')[0], 400)

    def test_votes_business_and_segment(self):
        v = lambda **k: self.req('/api/votes', {'business_id': 'B01', 'segment_id': None, 'choice': '일치', 'note': '', **k})[0]
        self.assertEqual(v(choice='유사중복 있음'), 400)
        self.assertEqual(v(choice='부분일치'), 400)            # 설명 필요
        self.assertEqual(v(segment_id='B02-S01'), 400)          # 다른 사업의 구획
        self.assertEqual(v(), 200)
        self.assertEqual(v(segment_id='B01-S01', choice='판단불가', note='2025 구획 범위 불명'), 200)
        saved = json.loads(self.votes.read_text(encoding='utf-8'))['votes']
        self.assertEqual(set(saved), {'B01', 'B01/B01-S01'})
        self.assertEqual(saved['B01']['decided_by'], 'human')
        self.assertNotEqual(self.votes, self.dataset)

    def test_open_and_origin(self):
        self.assertEqual(self.req('/api/open-source', {'doc': 'D1', 'target': 'file'})[0], 200)
        self.assertEqual(self.req('/api/open-source', {'doc': 'D2', 'target': 'file'})[0], 400)
        self.assertEqual(self.req('/api/open-source', {'doc': 'D2', 'target': 'directory'})[0], 200)
        self.assertEqual(self.req('/api/votes', {}, origin='http://evil.example')[0], 403)
        self.assertEqual(self.opened, [str(self.src), str(self.d)])


if __name__ == '__main__': unittest.main()
