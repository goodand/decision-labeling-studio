"""Datasette 0.65.5 기능 실측 (합성 파일만). 각 항목 결과를 표로 출력."""
import asyncio, hashlib, json, os, shutil, sqlite3, sys, pathlib
sys.stdout.reconfigure(encoding="utf-8")
from datasette.app import Datasette
from urllib.parse import quote
T=quote('사업목록')

ROOT = pathlib.Path(__file__).parent / "work"
shutil.rmtree(ROOT, ignore_errors=True)

def snap(d):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:12] for p in sorted(d.iterdir())}

def make(dirname, fname, wal=False, stray_wal=False, rows=1500):
    d = ROOT / dirname; d.mkdir(parents=True)
    p = d / fname
    c = sqlite3.connect(p)
    if wal: c.execute("pragma journal_mode=wal")
    c.execute('create table "사업목록" ("사업명" text, "내역" text, "금액" int)')
    c.executemany('insert into "사업목록" values (?,?,?)',
                  [(f"사업{i}", "패션 디자인 시제품 제작 지원" if i % 7 == 0 else "안전장치 보급", i) for i in range(rows)])
    c.commit()
    if wal:  # WAL 내용이 남은 상태로 두기 위해 체크포인트 없이 다른 커넥션 유지 후 복사
        c2 = sqlite3.connect(p); c2.execute('insert into "사업목록" values ("WAL행","x",0)'); c2.commit()
        shutil.copy(p, d / "_copy"); [shutil.copy(str(p)+s, str(d / "_copy")+s) for s in ("-wal",) if os.path.exists(str(p)+s)]
        c2.close(); c.close()
        for f in d.iterdir(): f.unlink() if f.name != "_copy" and not f.name.startswith("_copy") else None
        os.rename(d / "_copy", p)
        if (d / "_copy-wal").exists(): os.rename(d / "_copy-wal", str(p) + "-wal")
    else:
        c.close()
        if stray_wal: (d / (fname + "-wal")).write_bytes(b"")
    return p

cases = {
    "nonwal": make("plain", "예산.sqlite"),
    "wal": make("wal", "w.sqlite", wal=True),
    "stray": make("stray", "s.sqlite", stray_wal=True),
    "path#'": make("특수 #폴더's", "a#b's.sqlite"),
}

async def get(ds, url):
    r = await ds.client.get(url, follow_redirects=True)
    try: return r.status_code, r.json()
    except Exception: return r.status_code, r.text

async def main():
    out = []
    for name, p in cases.items():
        before = snap(p.parent)
        try:
            ds = Datasette(immutables=[str(p)], settings={"max_returned_rows": 1000})
            await ds.invoke_startup()
            db = list(ds.databases)[-1]; print("db이름", db)
            s, j = await get(ds, ds.urls.table(db,"사업목록")+f".json?_size=max&_shape=objects")
            s2, j2 = await get(ds, ds.urls.database(db)+f".json?sql=select+count(*)+as+n+from+사업목록&_shape=array")
            res = f"rows={len(j.get('rows',[]))} truncated?={j.get('truncated')} next={bool(j.get('next'))} count={j2}"
        except Exception as e:
            res = f"오류 {type(e).__name__}: {e}"[:160]
        after = snap(p.parent)
        out.append((name, res, "불변" if before == after else f"변경 {before} -> {after}"))
    for o in out: print("[원본]", *o)

    p = cases["nonwal"]
    ds = Datasette(immutables=[str(p)], settings={"max_returned_rows": 1000}); await ds.invoke_startup()
    db = list(ds.databases)[-1]
    sqls = {
        "1000행 초과 SELECT": "select * from 사업목록",
        "CTE DELETE": "with d as (delete from 사업목록 returning *) select * from d",
        "DELETE": "delete from 사업목록",
        "다중 문장": "select 1; select 2",
        "ATTACH": "attach database 'x.db' as x",
        "pragma 쓰기": "pragma user_version=5",
        "readfile류": "select load_extension('x')",
        "한글 열": 'select "사업명" from 사업목록 where "내역" like \'%패션%\' limit 2',
    }
    b0 = snap(p.parent)
    for k, q in sqls.items():
        r = await ds.client.get(ds.urls.database(db)+f".json", follow_redirects=True, params={"sql": q, "_shape": "objects"})
        try: j = r.json()
        except Exception: j = {"text": r.text[:120]}
        print("[SQL]", k, r.status_code, json.dumps({x: j.get(x) for x in ("ok", "error", "truncated")} | {"n": len(j.get("rows", []) or [])}, ensure_ascii=False))
    print("[SQL] 원본", "불변" if snap(p.parent) == b0 else "변경")
    s, j = await get(ds, ds.urls.table(db,"사업목록")+f".json?_search=패션")
    print("[검색] FTS 없음에서 _search:", s, str(j)[:150])
    s, j = await get(ds, ds.urls.table(db,"사업목록")+f".json?내역__contains=패션&_size=3")
    print("[검색] contains 필터:", s, j.get("filtered_table_rows_count") if isinstance(j, dict) else j)
    s, t = await get(ds, ds.urls.table(db,"사업목록"))
    print("[GUI] HTML 표 페이지:", s, "사업명" in str(t))
    print("[플러그인] hookspecs:", len([h for h in dir(__import__('datasette.hookspecs', fromlist=['x'])) if not h.startswith('_')]))

asyncio.run(main())
