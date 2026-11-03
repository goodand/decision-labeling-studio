"""엑셀→(calamine)→sqlite-utils→Datasette, FTS 한글 검색 실측. 합성 파일만."""
import asyncio, hashlib, io, pathlib, shutil, sys
sys.stdout.reconfigure(encoding="utf-8")
import openpyxl, sqlite_utils
from python_calamine import CalamineWorkbook
from datasette.app import Datasette

W = pathlib.Path(__file__).parent / "work2"; shutil.rmtree(W, ignore_errors=True)
src = W / "원본 폴더"; src.mkdir(parents=True); own = W / ".ldx"; own.mkdir()
x = src / "공고 마스터.xlsx"
wb = openpyxl.Workbook(); ws = wb.active; ws.title = "26마스터"
ws.append(["사업명", "내용"]); ws.append(["A사업", "패션 디자인 시제품을 제작하는 기업 지원"]); ws.append(["B사업", "산업현장 안전장치 보급"])
ws2 = wb.create_sheet("둘째 시트"); ws2.append(["코드", "비고"]); ws2.append(["P-2026-001", "안전장치는 별도"])
wb.save(x)
h0 = hashlib.sha256(x.read_bytes()).hexdigest(); l0 = sorted(p.name for p in src.iterdir())

cw = CalamineWorkbook.from_filelike(io.BytesIO(x.read_bytes()))
db = sqlite_utils.Database(own / "x.db")
for s in cw.sheet_names:
    rows = cw.get_sheet_by_name(s).to_python()
    hdr = [str(h) for h in rows[0]]
    db[s].insert_all([dict(zip(hdr, r)) | {"_행": i + 2} for i, r in enumerate(rows[1:])])
    db[s].enable_fts([c for c in hdr], tokenize="trigram", create_triggers=False)
print("원본 불변:", h0 == hashlib.sha256(x.read_bytes()).hexdigest() and l0 == sorted(p.name for p in src.iterdir()))
print("표:", db.table_names())

async def main():
    ds = Datasette(immutables=[str(own / "x.db")]); await ds.invoke_startup()
    for t in cw.sheet_names:
        for q in ["안전장치", "시제품", "시제품을 제작", "패션 시제품", "P-2026", "디자인시제품"]:
            r = await ds.client.get(ds.urls.table("x", t) + ".json", params={"_search": q, "_shape": "objects"}, follow_redirects=True)
            j = r.json(); print(f"  [{t}] '{q}': {r.status_code} {[o.get('_행') for o in j.get('rows', [])]}")
asyncio.run(main())
