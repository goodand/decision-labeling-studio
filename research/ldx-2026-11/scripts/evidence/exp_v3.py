"""판정표 v3 대책 실측 E1~E4 (합성 파일만)."""
import asyncio, csv, io, os, pathlib, shutil, sqlite3, sys
sys.stdout.reconfigure(encoding="utf-8")
W = pathlib.Path(__file__).parent / "work_exp"; shutil.rmtree(W, ignore_errors=True); W.mkdir()

# ---------- E1 세대별 사본 + 실행 중 Datasette 교체 ----------
from datasette.app import Datasette
from datasette.database import Database
def mk(p, n):
    c = sqlite3.connect(p); c.execute("create table t(x)"); c.executemany("insert into t values(?)", [(i,) for i in range(n)]); c.commit(); c.close()
async def e1():
    g1, g2 = W / "src1.1.db", W / "src1.2.db"; mk(g1, 100)
    ds = Datasette(); ds.add_database(Database(ds, path=str(g1), is_mutable=False), name="src1"); await ds.invoke_startup()
    q = lambda: ds.client.get("/src1.json", params={"sql": "select count(*) n from t", "_shape": "array"})
    print("E1 세대1:", (await q()).json())
    mk(g2, 250)                                       # scan이 새 세대 생성
    ds.remove_database("src1"); ds.add_database(Database(ds, path=str(g2), is_mutable=False), name="src1")
    print("E1 교체 후:", (await q()).json())
    try: g1.unlink(); print("E1 옛 세대 즉시 삭제: 성공")
    except Exception as e: print("E1 옛 세대 즉시 삭제: 실패", type(e).__name__)
    import gc; gc.collect()
    for d in [x for x in []]: pass
    try:
        if g1.exists(): g1.unlink()
        print("E1 gc 후 삭제:", not g1.exists())
    except Exception as e: print("E1 gc 후 삭제 실패", e)
asyncio.run(e1())

# ---------- E2 sqlite3 authorizer 쿼리 가드 ----------
mk(W / "q.db", 10)
def guarded(sql):
    con = sqlite3.connect((W / "q.db").resolve().as_uri() + "?immutable=1", uri=True)
    con.enable_load_extension(False) if hasattr(con, "enable_load_extension") else None
    con.execute("pragma query_only=1")
    ok = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
    con.set_authorizer(lambda a, b, c, d, e: sqlite3.SQLITE_OK if a in ok else sqlite3.SQLITE_DENY)
    if not sqlite3.complete_statement(sql.strip().rstrip(";") + ";") : return "거부(불완전)"
    try:
        cur = con.execute(sql)            # 다중 문장은 sqlite3가 ProgrammingError
        return f"허용 {cur.fetchall()[:2]}"
    except Exception as e: return f"거부 {type(e).__name__}: {str(e)[:50]}"
for s in ["select count(*) from t", "select * from t where x>7", "with a as (select 1) select * from a",
          "delete from t", "select 1; select 2", "select 1 --\n;drop table t", "attach database 'z.db' as z",
          "pragma user_version=3", "select load_extension('x')", "create table y(a)", "select readfile('q.db')",
          "insert into t values(1)", "with d as (delete from t returning *) select * from d"]:
    print("E2", repr(s)[:45].ljust(46), guarded(s))
print("E2 원본(q.db) 행 수 유지:", sqlite3.connect(W / "q.db").execute("select count(*) from t").fetchone())

# ---------- E3 trigram + 짧은 질의 LIKE + Kiwi 색인 열 ----------
from kiwipiepy import Kiwi
kiwi = Kiwi()
def kform(text):  # 명사·어근·영문·숫자 원형을 공백으로
    return " ".join(t.form for t in kiwi.tokenize(text) if t.tag[0] in "NSX" or t.tag in ("VV", "VA", "XR", "SL", "SN"))
rows = ["패션 디자인 시제품을 제작하는 기업 지원", "산업현장 안전장치 보급", "P-2026-001 과제 12개 지원", "디자인시제품 제작비"]
c = sqlite3.connect(":memory:")
c.execute("create virtual table f using fts5(txt, kw, tokenize='trigram')")
c.executemany("insert into f values(?,?)", [(r, kform(r)) for r in rows])
def search(q):
    if len(q.replace(" ", "")) < 3:
        hit = c.execute("select rowid from f where txt like ? or kw like ?", (f"%{q}%", f"%{q}%")).fetchall(); how = "LIKE"
    else:
        qq = " OR ".join(f'"{x}"' for x in {q, kform(q)} if x)
        hit = c.execute("select rowid from f where f match ?", (qq,)).fetchall(); how = "FTS"
    return how, sorted(h[0] for h in hit)
for q in ["패션", "디자", "12", "시제품", "시제품을", "디자인시제품", "디자인 시제품", "P-2026", "안전장치를", "제작하는"]:
    print("E3", q.ljust(10), search(q), "| kw:", kform(q))
print("E3 색인 kw 예:", [kform(r) for r in rows])

# ---------- E4 CSV 인코딩 판별 ----------
text = "사업명,금액\n안전장치 보급,100\n"
for name, data in [("utf8", text.encode("utf-8")), ("utf8bom", text.encode("utf-8-sig")), ("cp949", text.encode("cp949")), ("깨진", b"\xff\xfe\x00abc,\xc3")]:
    p = W / f"{name}.csv"; p.write_bytes(data)
    raw = p.read_bytes(); got = None
    for enc in ("utf-8-sig", "cp949"):
        try: got = (enc, list(csv.reader(io.StringIO(raw.decode(enc))))); break
        except UnicodeDecodeError: pass
    print("E4", name.ljust(8), got[0] if got else "판별 실패→limitation", got[1][0] if got else "")
