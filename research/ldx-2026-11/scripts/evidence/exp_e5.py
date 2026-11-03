"""E5: 실제 DB 사본에 FTS5 trigram 생성 크기·시간. 원본은 복사(읽기)만, 전후 폴더 목록 비교."""
import os, pathlib, shutil, sqlite3, sys, time
sys.stdout.reconfigure(encoding="utf-8")
src = pathlib.Path(sys.argv[1]); out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
side = [s for s in ("-wal", "-shm", "-journal") if pathlib.Path(str(src) + s).exists()]
before = sorted(os.listdir(src.parent))
t = time.time(); dst = out / "copy_g1.db"; shutil.copyfile(src, dst); tc = time.time() - t
after = sorted(os.listdir(src.parent))
print(f"원본 부속파일 {side or '없음'}, 복사 {dst.stat().st_size/1e6:.0f}MB {tc:.1f}s, 원본 폴더 불변={before == after}")
c = sqlite3.connect(dst)
tables = [r[0] for r in c.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
t0 = time.time(); total = 0
for tb in tables:
    cols = [r[1] for r in c.execute(f'pragma table_info("{tb}")') if (r[2] or "").upper() in ("TEXT", "") or "CHAR" in (r[2] or "").upper()]
    if not cols: continue
    t1 = time.time()
    collist = ", ".join(f'"{x}"' for x in cols)
    c.execute(f'create virtual table "{tb}__fts" using fts5({collist}, content="{tb}", content_rowid="rowid", tokenize="trigram")')
    c.execute(f'insert into "{tb}__fts"("{tb}__fts") values("rebuild")'); c.commit()
    total += 1
    if time.time() - t1 > 5: print(f"  {tb}: {len(cols)}열 {time.time()-t1:.0f}s")
c.execute("vacuum"); c.close()
size = dst.stat().st_size
print(f"FTS 표 {total}개, 생성 {time.time()-t0:.0f}s, 사본 {src.stat().st_size/1e6:.0f}MB → FTS 포함 {size/1e6:.0f}MB (×{size/src.stat().st_size:.2f})")
