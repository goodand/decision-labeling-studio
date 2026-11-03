"""F4: 실제 엑셀 → 변환 DB·FTS·Kiwi 사이드 표 크기 배율. 숫자만 출력, 변환 DB는 측정 후 삭제. 셀 내용 출력 금지."""
import io, os, pathlib, shutil, sqlite3, sys, time
sys.stdout.reconfigure(encoding="utf-8")
from python_calamine import CalamineWorkbook
import sqlite_utils
from kiwipiepy import Kiwi
src = pathlib.Path(sys.argv[1]); out = pathlib.Path(sys.argv[2]); shutil.rmtree(out, ignore_errors=True); out.mkdir(parents=True)
before = sorted(os.listdir(src.parent)); data = src.read_bytes(); after = sorted(os.listdir(src.parent))
print(f"원본 {len(data)/1e6:.2f}MB, 원본 폴더 불변={before == after}")
dbp = out / "x.db"; db = sqlite_utils.Database(dbp)
t0 = time.time(); wb = CalamineWorkbook.from_filelike(io.BytesIO(data)); nt = 0
for i, s in enumerate(wb.sheet_names):
    rows = wb.get_sheet_by_name(s).to_python()
    if not rows: continue
    hdr, seen = [], {}
    for j, h in enumerate(rows[0]):
        h = str(h).strip() or f"col{j+1}"; n = seen.get(h, 0); seen[h] = n + 1; hdr.append(h if n == 0 else f"{h}_{n+1}")
    recs = [dict(zip(hdr, r)) | {"_source_row": k + 2} for k, r in enumerate(rows[1:])]
    if recs: db[f"s{i}"].insert_all(recs, alter=True); nt += 1
tconv = time.time() - t0; db.vacuum(); s_tab = dbp.stat().st_size
t0 = time.time()
for t in db.table_names():
    cols = [c.name for c in db[t].columns if c.type == "TEXT"]
    if cols: db[t].enable_fts(cols, tokenize="trigram")
tfts = time.time() - t0; db.vacuum(); s_fts = dbp.stat().st_size
kiwi = Kiwi(); t0 = time.time(); chars = 0
for t in [x for x in db.table_names() if not x.endswith(("_fts", "_data", "_idx", "_docsize", "_config")) and x.startswith("s")]:
    cols = [c.name for c in db[t].columns if c.type == "TEXT"]
    if not cols: continue
    db.execute(f'create virtual table "{t}__kw" using fts5(m, tokenize="unicode61")')
    for row in db.execute(f'select rowid, {", ".join(chr(34)+c+chr(34) for c in cols)} from "{t}"').fetchall():
        txt = " ".join(str(v) for v in row[1:] if v); chars += len(txt)
        ms = [k.form for k in kiwi.tokenize(txt) if k.tag.startswith(("NN", "SL", "SN", "XR", "VV", "VA"))] if txt else []
        db.execute(f'insert into "{t}__kw"(rowid, m) values(?, ?)', (row[0], " ".join(ms)))
db.conn.commit(); tkw = time.time() - t0; db.vacuum(); s_kw = dbp.stat().st_size; db.close()
o = len(data)
print(f"시트 표 {nt}개, 변환 {tconv:.1f}s → 표만 {s_tab/1e6:.1f}MB (×{s_tab/o:.1f})")
print(f"원문 trigram FTS {tfts:.1f}s → {s_fts/1e6:.1f}MB (×{s_fts/o:.1f})")
print(f"Kiwi 사이드 표 {tkw:.1f}s, {chars:,}자({chars/max(tkw,1e-9)/1e4:.0f}만 자/초) → {s_kw/1e6:.1f}MB (×{s_kw/o:.1f})")
shutil.rmtree(out); print("변환 DB 삭제:", not out.exists())
