"""셀 전체 색인 크기 추정: 텍스트 셀 수·문자 수 (원본 읽기 전용, 전후 폴더 목록 비교)."""
import os, sqlite3, sys, time, pathlib
sys.stdout.reconfigure(encoding="utf-8")

def sqlite_text(path):
    p = pathlib.Path(path)
    before = sorted(os.listdir(p.parent))
    con = sqlite3.connect(p.as_uri() + "?immutable=1", uri=True)
    cells = chars = 0
    per = []
    for (t,) in con.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'"):
        cols = [r[1] for r in con.execute(f'pragma table_info("{t}")') if (r[2] or "").upper() in ("TEXT", "") or "CHAR" in (r[2] or "").upper()]
        if not cols:
            continue
        expr = " + ".join(f'coalesce(length("{c}"),0)' for c in cols)
        nn = " + ".join(f'("{c}" is not null and typeof("{c}")=\'text\')' for c in cols)
        n, ch = con.execute(f'select sum({nn}), sum({expr}) from "{t}"').fetchone()
        cells += n or 0; chars += ch or 0
        per.append((ch or 0, t, n or 0))
    con.close()
    after = sorted(os.listdir(p.parent))
    per.sort(reverse=True)
    return cells, chars, per[:5], before == after

def xlsx_text(path):
    from python_calamine import CalamineWorkbook
    p = pathlib.Path(path)
    before = sorted(os.listdir(p.parent))
    data = p.read_bytes()
    wb = CalamineWorkbook.from_filelike(__import__("io").BytesIO(data))
    cells = chars = 0
    for s in wb.sheet_names:
        for row in wb.get_sheet_by_name(s).to_python():
            for v in row:
                if isinstance(v, str) and v:
                    cells += 1; chars += len(v)
    after = sorted(os.listdir(p.parent))
    return cells, chars, len(wb.sheet_names), before == after

for path in sys.argv[1:]:
    t0 = time.time()
    size = os.path.getsize(path) / 1e6
    if path.endswith(".xlsx"):
        cells, chars, nsheets, same = xlsx_text(path)
        print(f"{size:7.0f}MB  텍스트 셀 {cells:,}  문자 {chars:,}  시트 {nsheets}  폴더불변={same}  {time.time()-t0:.0f}s  {pathlib.Path(path).name}")
    else:
        cells, chars, top, same = sqlite_text(path)
        print(f"{size:7.0f}MB  텍스트 셀 {cells:,}  문자 {chars:,}  폴더불변={same}  {time.time()-t0:.0f}s  {pathlib.Path(path).name}")
        for ch, t, n in top:
            print(f"           상위 테이블 {t}: 셀 {n:,} 문자 {ch:,}")
