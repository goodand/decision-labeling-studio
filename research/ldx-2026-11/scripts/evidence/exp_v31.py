"""판정표 v3.1 대책 실측 F1~F3 (합성 파일만)."""
import os, pathlib, shutil, sqlite3, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
W = pathlib.Path(__file__).parent / "work_f"; shutil.rmtree(W, ignore_errors=True); W.mkdir()
RO = lambda p: sqlite3.connect(pathlib.Path(p).resolve().as_uri() + "?mode=ro&immutable=1", uri=True)

# ---------- F1 부속 파일 이름 맞춰 복사 → 사본 복구 → quick_check ----------
SIDE = ("-wal", "-journal")
def snapshot(src, dst):
    for s in ("",) + SIDE:
        p = pathlib.Path(str(src) + s)
        if p.exists(): shutil.copyfile(p, str(dst) + s)       # 원본 x.sqlite-wal → 사본 ID.db-wal
    c = sqlite3.connect(dst)                                  # 읽기·쓰기로 열어 롤백/체크포인트 유도
    c.execute("pragma wal_checkpoint(TRUNCATE)") if c.execute("pragma journal_mode").fetchone()[0] == "wal" else None
    c.execute("pragma journal_mode=delete"); qc = c.execute("pragma quick_check").fetchone()[0]; c.close()
    for s in SIDE + ("-shm",):
        pathlib.Path(str(dst) + s).unlink(missing_ok=True)
    return qc

# (a) 핫 저널: 다른 프로세스가 큰 트랜잭션 도중 멈춘 상태를 만든다
hot = W / "hot.sqlite"
c = sqlite3.connect(hot); c.execute("pragma journal_mode=delete"); c.execute("create table t(a,b)")
c.executemany("insert into t values(1,?)", [("x" * 200,) for _ in range(20000)]); c.commit(); c.close()
child = f"""
import sqlite3,time
c=sqlite3.connect(r'{hot}'); c.execute('pragma cache_size=10')
c.execute('begin'); c.execute('update t set a=2'); time.sleep(30)
"""
p = subprocess.Popen([sys.executable, "-c", child]); time.sleep(3)
print("F1a 원본 폴더:", sorted(x.name for x in W.iterdir()))
bad = W / "bad_body_only.db"; shutil.copyfile(hot, bad)
cb = sqlite3.connect(bad)
print("F1a 본체만 복사: a=2 행", cb.execute("select count(*) from t where a=2").fetchone()[0], "전체", cb.execute("select count(*) from t").fetchone()[0], "quick_check", cb.execute("pragma quick_check").fetchone()[0][:40]); cb.close()
good = W / "ID1.db"; qc = snapshot(hot, good)
cg = RO(good); print("F1a 이름 맞춰 복사+복구: a=2 행", cg.execute("select count(*) from t where a=2").fetchone()[0], "전체", cg.execute("select count(*) from t").fetchone()[0], "quick_check", qc); cg.close()
p.kill(); p.wait()

# (b) WAL: 커밋됐지만 체크포인트 안 된 내용
wal = W / "w.sqlite"
c = sqlite3.connect(wal); c.execute("pragma journal_mode=wal"); c.execute("pragma wal_autocheckpoint=0")
c.execute("create table t(x)"); c.executemany("insert into t values(?)", [(i,) for i in range(500)]); c.commit()
c2 = sqlite3.connect(wal)                                    # 연결 유지 → 체크포인트 없이 -wal 남김
st = lambda: tuple((pathlib.Path(str(wal) + s).stat().st_size if pathlib.Path(str(wal) + s).exists() else -1) for s in ("", "-wal"))
print("F1b (본체, -wal) 크기:", st())
w1 = W / "ID2.db"; print("F1b 이름 맞춰 복사 quick_check:", snapshot(wal, w1), "행", RO(w1).execute("select count(*) from t").fetchone()[0])
w0 = W / "ID3.db"; shutil.copyfile(wal, w0); shutil.copyfile(str(wal) + "-wal", str(wal) + ".copy-wal")
try: print("F1b 원래 이름으로 부속 복사: 행", sqlite3.connect(w0).execute("select count(*) from t").fetchone()[0])
except Exception as e: print("F1b 원래 이름으로 부속 복사:", e)
c2.close(); c.close()

# ---------- F2 확장 쿼리 가드 + 시간 상한 ----------
q = W / "q.db"; c = sqlite3.connect(q)
c.execute("create table t(x, s)"); c.executemany("insert into t values(?,?)", [(i, f"패션 시제품 {i}") for i in range(2000)])
c.execute("create virtual table f using fts5(s, tokenize='trigram')"); c.execute("insert into f select s from t"); c.commit(); c.close()
OKA = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
OKP = {"data_version", "table_info", "table_xinfo", "index_list"}
def guard(sql, limit_s=1.0):
    con = RO(q); con.enable_load_extension(False); con.execute("pragma query_only=1")
    con.set_authorizer(lambda a, x, y, z, w: sqlite3.SQLITE_OK if a in OKA or (a == sqlite3.SQLITE_PRAGMA and x in OKP) else sqlite3.SQLITE_DENY)
    t0 = time.time(); con.set_progress_handler(lambda: 1 if time.time() - t0 > limit_s else 0, 10000)
    try: return f"허용 {con.execute(sql).fetchall()[:1]}"
    except Exception as e: return f"거부 {type(e).__name__}: {str(e)[:40]}"
for s in ["select count(*) from f where f match '시제품'", "with recursive n(i) as (select 1 union all select i+1 from n where i<5) select count(*) from n",
          "select name from pragma_table_info('t')", "select count(*) from t", "pragma user_version=1", "pragma data_version=1",
          "delete from t", "attach 'z.db' as z", "select 1; select 2", "select load_extension('x')",
          "select count(*) from t a, t b, t c"]:
    print("F2", repr(s)[:48].ljust(50), guard(s))

# ---------- F3 단어별 검색: 원문 trigram + Kiwi 사이드 표(unicode61) + 짧은 단어 LIKE ----------
from kiwipiepy import Kiwi
import sqlite_utils
kiwi = Kiwi()
def morphs(text):
    return [t.form for t in kiwi.tokenize(text) if t.tag.startswith(("NN", "SL", "SN", "XR", "VV", "VA")) and (len(t.form) > 1 or t.tag in ("SN", "SL"))]
rows = ["패션 디자인 시제품을 제작하는 기업 지원", "산업현장 안전장치 보급", "P-2026-001 과제 12개 지원", "디자인시제품 제작비", "창업 기업 융자 지원", "패션 브랜드 해외 진출"]
db = sqlite_utils.Database(memory=True)
db["시트1"].insert_all([{"_source_row": i + 2, "내용": r} for i, r in enumerate(rows)])
db["시트1"].enable_fts(["내용"], tokenize="trigram")
db.execute("create virtual table kw using fts5(m, tokenize='unicode61')")   # 사이드 표, rowid = 원 표 rowid
for rid, txt in db.execute("select rowid, 내용 from 시트1").fetchall():
    db.execute("insert into kw(rowid, m) values(?, ?)", (rid, " ".join(morphs(txt))))
print("F3 사용자 표 열(노출 확인):", [c.name for c in db["시트1"].columns])
def search(q):
    terms = q.split(); conds, args = [], []
    for w in terms:
        ms = morphs(w) or [w]
        alt = []
        for m in ms:                                        # 형태소 하나라도 맞으면 그 단어 충족
            alt.append("rowid in (select rowid from kw where kw match ?)"); args.append('"' + m.replace('"', '') + '"')
            if len(m) >= 3: alt.append("rowid in (select rowid from 시트1_fts where 시트1_fts match ?)"); args.append('"' + m + '"')
            else: alt.append("내용 like ?"); args.append(f"%{m}%")
        if len(w) >= 3: alt.append("rowid in (select rowid from 시트1_fts where 시트1_fts match ?)"); args.append('"' + w.replace('"', '') + '"')
        else: alt.append("내용 like ?"); args.append(f"%{w}%")
        conds.append("(" + " or ".join(alt) + ")")
    return [r[0] for r in db.execute(f"select _source_row from 시트1 where {' and '.join(conds)}", args).fetchall()]
for qq in ["패션", "패션을", "기업을", "융자를", "창업을", "시제품 디자인", "패션 시제품", "디자인시제품", "12 지원", "P-2026", "안전장치를", "제작하는", "패션 디자인 시제품"]:
    print("F3", qq.ljust(12), search(qq))
t0 = time.time(); kiwi.tokenize("패션 디자인 시제품"); print(f"F3 Kiwi 로드 후 tokenize {time.time()-t0:.3f}s")
