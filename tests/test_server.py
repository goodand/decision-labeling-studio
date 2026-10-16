"""Meaningful API regressions for portable datasets. Author: chatgpt_gpt6."""
import importlib.util
import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('studio_server', ROOT / 'studio_server.py')
studio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(studio)


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def start(self, kind):
        import shutil
        shutil.copytree(ROOT / 'datasets' / kind, self.directory / kind)
        self.dataset = self.directory / kind / 'dataset.json'
        self.votes = self.directory / 'votes.json'
        self.http = studio.make_server(self.dataset, self.votes, 0)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.http.shutdown)
        self.url = f'http://127.0.0.1:{self.http.server_port}'

    def request(self, path, data=None, origin=None):
        headers = {'Content-Type': 'application/json'}
        if origin: headers['Origin'] = origin
        req = urllib.request.Request(self.url + path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
        try:
            with urllib.request.urlopen(req) as response:
                raw = response.read()
                return response.status, json.loads(raw) if 'json' in response.headers.get('Content-Type', '') else raw
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_capture_save_restart_and_missing_candidate(self):
        self.start('capture-demo')
        status, payload = self.request('/api/cases')
        self.assertEqual(status, 200)
        self.assertEqual(len(payload['cases']), 2)
        self.assertTrue(all(c['case_id'].startswith('sample-') for c in payload['cases']))
        self.assertEqual(self.request('/api/source-page?case=sample-1&page=1')[0], 200)
        self.assertEqual(self.request('/api/decision', {'case_id':'sample-1','choice':'accurate','reason':'','candidate_rank':1,'candidate_mode':'raw'})[0], 200)
        saved = studio.load_dataset(self.dataset)
        self.assertEqual(studio.read_votes(self.votes, saved)['decisions']['sample-1']['choice'], 'accurate')
        self.assertEqual(self.request('/api/decision', {'case_id':'sample-2','choice':'error','candidate_rank':None,'candidate_mode':None})[0], 200)

    def test_capture_rejects_invalid_reason_rank_and_origin(self):
        self.start('capture-demo')
        base={'case_id':'sample-1','choice':'undecidable','reason':'','candidate_rank':1,'candidate_mode':'raw'}
        self.assertEqual(self.request('/api/decision', base)[0], 400)
        self.assertEqual(self.request('/api/decision', {**base,'reason':'cannot tell','candidate_rank':99})[0], 400)
        self.assertEqual(self.request('/api/decision', {**base,'reason':'cannot tell'}, 'https://example.org')[0], 403)
        self.assertFalse(self.votes.exists())

    def test_record_save_and_dataset_change_rejected(self):
        self.start('record-demo')
        self.assertEqual(self.request('/api/source-preview?row=1')[1]['page_count'], 2)
        self.assertEqual(self.request('/api/vote', {'excel_row':1,'choice':'wrong','note':''})[0], 400)
        self.assertEqual(self.request('/api/vote', {'excel_row':1,'choice':'correct','note':''})[0], 200)
        record=json.loads(self.votes.read_text(encoding='utf-8'))['votes']['1']
        self.assertEqual(record['case_id'], 'item-alpha')
        self.dataset.write_text(self.dataset.read_text(encoding='utf-8')+' ', encoding='utf-8')
        self.assertEqual(self.request('/api/vote', {'excel_row':2,'choice':'correct','note':''})[0], 409)
        with self.assertRaises(ValueError): studio.read_votes(self.votes, studio.load_dataset(self.dataset))

    def test_asset_change_rejected(self):
        self.start('capture-demo')
        asset=self.directory/'capture-demo'/'page.svg'
        asset.write_text(asset.read_text(encoding='utf-8')+' ',encoding='utf-8')
        self.assertEqual(self.request('/api/source-page?case=sample-1&page=1')[0],409)
        self.assertEqual(self.request('/api/decision', {'case_id':'sample-1','choice':'error','candidate_rank':1,'candidate_mode':'raw'})[0],409)

    def test_unknown_paths_and_cases_do_not_write(self):
        self.start('record-demo')
        self.assertEqual(self.request('/api/source-page?row=999&page=1')[0],404)
        self.assertEqual(self.request('/api/vote', {'excel_row':999,'choice':'correct','note':''})[0],400)
        self.assertEqual(self.request('/api/open-source-directory', {'excel_row':1})[0],404)
        self.assertFalse(self.votes.exists())

    def test_dataset_path_escape_and_empty_input(self):
        path=self.directory/'dataset.json'
        path.write_text(json.dumps({'kind':'capture','cases':[]}),encoding='utf-8')
        with self.assertRaises(ValueError): studio.load_dataset(path)
        path.write_text(json.dumps({'kind':'capture','pages':['../outside.svg'],'cases':[{'id':'x','label':'x','page':1,'source_page_size':[100,100],'source_bbox':[0,0,10,10],'candidates':[]}]}),encoding='utf-8')
        with self.assertRaises(ValueError): studio.load_dataset(path)

    def test_arbitrary_dataset_ids_and_counts_are_not_workload_constants(self):
        self.start('capture-demo')
        data=json.loads(self.dataset.read_text(encoding='utf-8'))
        data['cases']=[{**data['cases'][0],'id':'new-dataset-item','label':'Independent dataset'}]
        replacement=self.dataset.parent/'replacement.json'
        replacement.write_text(json.dumps(data),encoding='utf-8')
        loaded=studio.load_dataset(replacement)
        self.assertEqual(len(loaded['cases']),1)
        self.assertEqual(loaded['cases'][0]['case_id'],'new-dataset-item')
        self.assertNotEqual(loaded['input_sha256'],studio.load_dataset(self.dataset)['input_sha256'])

if __name__ == '__main__': unittest.main()
