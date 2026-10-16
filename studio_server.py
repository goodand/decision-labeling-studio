"""Dataset adapters for preserved review UIs. Author: chatgpt_gpt6.

Python 3.10+, standard library only. Original documents remain outside this repo;
adapters consume pre-rendered image pages, records and extraction candidates.
"""
import argparse
import base64
import hashlib
import json
import math
import mimetypes
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_dataset(path):
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if data.get('kind') not in ('capture', 'record') or not isinstance(data.get('cases'), list) or not data['cases']:
        raise ValueError('kind must be capture or record, with nonempty cases')
    assets = {}

    def asset(name):
        if not isinstance(name, str) or not name or Path(name).is_absolute():
            raise ValueError('Asset paths must be dataset-relative')
        p = (path.parent / name).resolve()
        if not p.is_relative_to(path.parent) or not p.is_file() or p.suffix.lower() not in ('.svg', '.png', '.jpg', '.jpeg', '.webp'):
            raise ValueError('Missing image or image path outside dataset directory')
        assets[name] = {'path': p, 'sha256': digest(p)}
        return name

    pages = [asset(n) for n in data.get('pages', [])]
    if not pages: raise ValueError('pages must contain at least one pre-rendered image')
    ids = set()
    cases = []
    for i, item in enumerate(data['cases'], 1):
        case_id = item.get('id')
        if not isinstance(case_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', case_id) or case_id in ids:
            raise ValueError('Case ids must be unique ASCII letters, digits, hyphens or underscores')
        ids.add(case_id)
        label = item.get('label')
        if not isinstance(label, str) or not label: raise ValueError('Each case needs a label')
        page = item.get('page', 1)
        if type(page) is not int or not 1 <= page <= len(pages): raise ValueError('Invalid source page')
        if data['kind'] == 'capture':
            size, box = item.get('source_page_size'), item.get('source_bbox')
            if not isinstance(size, list) or len(size) != 2 or not isinstance(box, list) or len(box) != 4 or not all(type(x) in (int,float) and math.isfinite(x) for x in size + box):
                raise ValueError('Capture needs finite source_page_size and source_bbox')
            w,h = size; x0,y0,x1,y1 = box
            if not (w > 0 and h > 0 and 0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h): raise ValueError('Invalid bounding box')
            candidates = []
            if not isinstance(item.get('candidates', []), list): raise ValueError('candidates must be a list')
            for rank, candidate in enumerate(item.get('candidates', []), 1):
                images = {mode: {'url': f'/api/extracted/{case_id}/{rank}/{mode}', '_asset': asset(name)} for mode,name in candidate.items() if mode in ('raw','composite')}
                if not images: raise ValueError('Candidate needs raw or composite image')
                candidates.append({'rank':rank,'images':images})
            cases.append({'case_id':case_id,'label':label,'page':page,'source_page_size':size,'source_bbox':box,'candidates':candidates})
        else:
            refs = item.get('candidates', [])
            fields = item.get('fields', [])
            if not isinstance(refs,list) or not all(isinstance(r,dict) for r in refs): raise ValueError('record candidates must be objects')
            if not isinstance(fields,list) or not all(isinstance(f,dict) and isinstance(f.get('label'),str) for f in fields): raise ValueError('fields need label/value objects')
            hits = item.get('match_pages', [page])
            if not isinstance(hits,list) or not all(type(p) is int and 1 <= p <= len(pages) for p in hits): raise ValueError('Invalid match_pages')
            cases.append({'case_id':case_id,'excel_row':i,'excel_name':label,'agency':item.get('group',''),
                          'priority':bool(item.get('priority',True)), 'priority_labels':[],
                          'state':'exact_name_candidate' if refs else 'no_candidate',
                          'exact_candidate_refs':refs, 'reference_fields':fields, '_page':page,'_hits':hits})
    identity = hashlib.sha256(json.dumps({'input':digest(path),'assets':{n:x['sha256'] for n,x in sorted(assets.items())}},sort_keys=True).encode()).hexdigest()
    return {'path':path,'kind':data['kind'],'title':data.get('title','Review dataset'),'question':data.get('question'),
            'pages':pages,'assets':assets,'cases':cases,'input_sha256':identity,'dataset_sha256':digest(path)}


def read_votes(path, context):
    if not path.exists(): return {'schema':'studio-votes/v1','input_sha256':context['input_sha256'],'decisions':{},'votes':{}}
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema') != 'studio-votes/v1' or data.get('input_sha256') != context['input_sha256'] or not all(isinstance(data.get(k),dict) for k in ('decisions','votes')):
        raise ValueError('Vote file belongs to a different dataset revision; keep it and choose another --votes path')
    return data


def atomic_save(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.studio-',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally: Path(name).unlink(missing_ok=True)


def make_server(dataset, votes, port=0):
    context=load_dataset(dataset); votes=Path(votes).resolve(); read_votes(votes,context)
    if votes == context['path'] or votes in [a['path'] for a in context['assets'].values()]: raise ValueError('votes must not overwrite dataset assets')
    lock=threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass

        def send(self,status,payload,mime='application/json'):
            raw=json.dumps(payload,ensure_ascii=False).encode('utf-8') if mime=='application/json' else payload
            self.send_response(status);self.send_header('Content-Type',mime+('; charset=utf-8' if mime.startswith('text/') or mime=='application/json' else ''))
            self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)

        def fresh(self):
            return digest(context['path'])==context['dataset_sha256'] and all(digest(a['path'])==a['sha256'] for a in context['assets'].values())

        def asset(self,name):
            a=context['assets'][name]
            self.send(200,a['path'].read_bytes(),mimetypes.guess_type(name)[0] or 'application/octet-stream')

        def do_GET(self):
            try:
                url=urlsplit(self.path);q=parse_qs(url.query);path=unquote(url.path)
                if path.startswith('/api/'):
                    if not self.fresh(): return self.send(409,{'error':'Dataset or evidence changed; restart with a new vote file'})
                    if path=='/api/cases':
                        saved=read_votes(votes,context)
                        cases=json.loads(json.dumps(context['cases']))
                        for c in cases:
                            c.pop('_page',None);c.pop('_hits',None)
                            for candidate in c.get('candidates',[]):
                                for image in candidate['images'].values(): image['sha256']=context['assets'][image.pop('_asset')]['sha256']
                        return self.send(200,{'cases':cases,'decisions':saved['decisions'],'votes':saved['votes'],
                                              'page_count':len(context['pages']),'input_sha256':context['input_sha256'],
                                              'dataset_title':context['title'],'question':context['question']})
                    if path in ('/api/source-page','/api/source-crop','/api/source-preview'):
                        if context['kind']=='capture': c=next((c for c in context['cases'] if c['case_id']==q.get('case',[''])[0]),None)
                        else: c=next((c for c in context['cases'] if str(c['excel_row'])==q.get('row',[''])[0]),None)
                        if c is None: return self.send(404,{'error':'Unknown case'})
                        if path=='/api/source-preview': return self.send(200,{'status':'ready','page_count':len(context['pages']),'suggested_page':c['_page'],'hits':c['_hits']})
                        if path=='/api/source-crop':
                            a=context['assets'][context['pages'][c['page']-1]];mime=mimetypes.guess_type(a['path'].name)[0];encoded=base64.b64encode(a['path'].read_bytes()).decode()
                            x0,y0,x1,y1=c['source_bbox'];w,h=c['source_page_size']
                            svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0} {y0} {x1-x0} {y1-y0}"><image width="{w}" height="{h}" href="data:{mime};base64,{encoded}"/></svg>'
                            return self.send(200,svg.encode(),'image/svg+xml')
                        page=int(q.get('page',['1'])[0])
                        if not 1 <= page <= len(context['pages']): return self.send(404,{'error':'Unknown page'})
                        return self.asset(context['pages'][page-1])
                    m=re.fullmatch(r'/api/extracted/([A-Za-z0-9_-]+)/(\d+)/(raw|composite)',path)
                    if m and context['kind']=='capture':
                        c=next((c for c in context['cases'] if c['case_id']==m[1]),None);rank=int(m[2])
                        if c and 1<=rank<=len(c['candidates']):
                            image=c['candidates'][rank-1]['images'].get(m[3])
                            if image: return self.asset(image['_asset'])
                    return self.send(404,{'error':'Unknown API endpoint'})
                if path=='/': path='/ui/capture.html' if context['kind']=='capture' else '/ui/review_index.html'
                file=(ROOT/path.lstrip('/')).resolve()
                if file.is_relative_to(ROOT/'ui') and file.is_file() and file.suffix in ('.html','.css','.js'):
                    return self.send(200,file.read_bytes(),mimetypes.guess_type(file.name)[0] or 'text/plain')
                return self.send(404,{'error':'Not found'})
            except (OSError,ValueError,TypeError,KeyError) as exc: self.send(400,{'error':str(exc)})

        def do_POST(self):
            try:
                if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}' or self.headers.get('Origin') not in (None,f'http://127.0.0.1:{self.server.server_port}'):
                    return self.send(403,{'error':'Use this local server origin'})
                expected='/api/decision' if context['kind']=='capture' else '/api/vote'
                if self.path!=expected: return self.send(404,{'error':'Unknown API endpoint'})
                if self.headers.get('Content-Type','').split(';')[0]!='application/json': raise ValueError('Expected JSON')
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=16384: raise ValueError('Invalid request size')
                request=json.loads(self.rfile.read(length))
                if not isinstance(request,dict): raise ValueError('Expected object')
                if not self.fresh(): return self.send(409,{'error':'Dataset or evidence changed'})
                capture=context['kind']=='capture'
                c=next((c for c in context['cases'] if (c['case_id']==request.get('case_id') if capture else c['excel_row']==request.get('excel_row'))),None)
                allowed=('accurate','error','undecidable') if capture else ('correct','wrong','undecidable')
                choice=request.get('choice');reason=request.get('reason' if capture else 'note','')
                if c is None or choice not in allowed or not isinstance(reason,str) or len(reason)>4000: raise ValueError('Invalid case, choice or note')
                if (choice=='undecidable' or not capture and choice=='wrong') and not reason.strip(): raise ValueError('Reason required')
                record={'case_id':c['case_id'],'choice':choice,'reason' if capture else 'note':reason.strip(),
                        'updated_at_utc':datetime.now(timezone.utc).isoformat(),'submitted_via':'local_review_ui'}
                if capture:
                    rank,mode=request.get('candidate_rank'),request.get('candidate_mode')
                    if c['candidates']:
                        if type(rank) is not int or not 1<=rank<=len(c['candidates']) or not isinstance(mode,str) or mode not in c['candidates'][rank-1]['images']: raise ValueError('Invalid candidate')
                        name=c['candidates'][rank-1]['images'][mode]['_asset'];record['candidate_sha256']=context['assets'][name]['sha256']
                    elif rank is not None or mode is not None: raise ValueError('No candidates for this case')
                    record.update(candidate_rank=rank,candidate_mode=mode,page=c['page'])
                else: record['excel_row']=c['excel_row']
                with lock:
                    saved=read_votes(votes,context);saved['decisions' if capture else 'votes'][c['case_id'] if capture else str(c['excel_row'])]=record
                    atomic_save(votes,saved)
                self.send(200,{'saved':True,'decision' if capture else 'vote':record})
            except (OSError,ValueError,TypeError,KeyError) as exc: self.send(400,{'error':str(exc)})

    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--votes',type=Path,required=True)
    parser.add_argument('--port',type=int,default=0)
    args=parser.parse_args();http=make_server(args.dataset,args.votes,args.port)
    print(json.dumps({'url':f'http://127.0.0.1:{http.server_port}/','votes':str(args.votes.resolve())}),flush=True)
    try: http.serve_forever()
    except KeyboardInterrupt: pass
    finally: http.server_close()

if __name__=='__main__': main()
