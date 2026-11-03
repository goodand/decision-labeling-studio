# Datasette 재사용 적합성 실측 (2026-11-03)

환경: PyPI datasette 0.65.5, sqlite-utils, python-calamine, datasette-search-all. 격리 venv, 합성 파일만. 스크립트: scripts/evidence/probe_ds.py, probe_xlsx_fts.py

| 기능 | 결과 | 판정 |
|---|---|---|
| `-i`(immutable)로 일반 DB 열기 | 1,500행 조회, 원본 폴더 해시·목록 불변 | 재사용 |
| 비WAL + 빈 `-wal` 잔존 | 정상 조회, 부속 파일 생성 없음 | 재사용 |
| **WAL DB(내용이 `-wal`에 있음)** | 오류 없이 열리나 표가 없음(`no such table`). `immutable=1`이 WAL을 무시. 사본(본체+`-wal`) 복사 → 사본에서 체크포인트·journal_mode=delete → `-i`로 열면 1,501행 전부 조회, 원본 해시·목록 불변 | **원본 직접 열면 조용한 누락**. 체크포인트한 사본은 재사용 가능 |
| **경로에 `#`** | `f"file:{path}?immutable=1"` 비이스케이프(database.py connect) → 엉뚱한 빈 DB, 오류 없음 | **조용한 누락**. `.ldx` 안 안전한 이름의 사본만 연다 |
| 결과 한도 | SQL 1,500행 → 1,000행 + `truncated:true`. 표 API는 `truncated:false` + `next` 커서 | 봉투의 truncated는 두 경우를 합쳐 계산 |
| 쓰기 차단 | DELETE·ATTACH·pragma 쓰기 "Statement must be a SELECT", 다중 문장 거부, load_extension "not authorized", CTE DELETE는 SQLite 문법 오류 | 재사용 |
| 한글 표·열·`like` | 정상 | 재사용 |
| `contains` 필터 | 215건(1,500 중 7의 배수) 정확 | 재사용 |
| **FTS 없는 표에 `_search`** | 오류 없이 무시하고 전체 행 반환 | **조용한 오답**. 검색 대상 표는 FTS 존재를 확인 |
| 엑셀 → calamine → sqlite-utils(`.ldx` 안) | 원본 해시·폴더 불변, 시트별 표 생성, `_행` 열로 원래 행 번호 유지 | 재사용 |
| FTS5 trigram 한글 | "안전장치", "시제품", "시제품을 제작", "패션 시제품", "P-2026" 찾음. "디자인시제품"(띄어쓰기 다름) 못 찾음 | 재사용. 띄어쓰기 변이는 Kiwi 보완 필요 |
| 모든 시트 검색(datasette-search-all) | 설치·화면 200, 두 시트 이름 표시 | 결과 내용은 미확인(화면이 JS로 결과를 그릴 수 있음) |
| 플러그인 훅 | 30개(register_routes 등) | 대조 화면을 플러그인으로 만들 수 있음 |

## 결론
- Datasette는 GUI, JSON API, SELECT 전용 SQL, 필터, FTS 검색을 덮는다. 단 **원본에 직접 쓰지 않는다.**
- 구조: 원본 → (ldx 접착 코드: 부속 파일 판별, 체크포인트 스냅샷, 엑셀 변환) → `.ldx/` 사본 → Datasette `-i`.
- 직접 짤 부분: 스냅샷·변환, 봉투의 `limitations`·`read_completeness`, FTS 존재 검사, Kiwi 띄어쓰기 보완, 대조 플러그인.
- 미측정: datasette-search-all 결과 내용, 대용량(2.2GB) 변환 시간.
