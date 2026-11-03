# 2차 벤치마킹: Datasette, Harlequin (코드 읽기 + 메인 실측)

기준: [criteria.md](criteria.md) v1. 코드 평가: sonnet 서브에이전트. ✔ = 메인이 코드 또는 실측으로 직접 확인.

| 기준 (가중치) | Datasette (d1cc495, Apache-2.0) | Harlequin (ad3ecef, MIT) |
|---|---|---|
| C1 원본 불변 (25) | 4 — 변경 가능 DB는 `?mode=ro`, `-i` DB는 `?immutable=1`, `-i`는 쓰기 연결 assert로 차단 ✔ (`datasette/database.py:194-207`). 쓰기 권한은 기본 허용 목록에 없음 | 2 — 기본이 읽기·쓰기: `read_only=False`이고 옵션 없으면 모드 문자열 빈 값 ✔ (`src/harlequin_sqlite/adapter.py:428,483-493`). `--read-only`를 명시해야 `?mode=ro` |
| C2 로컬 파일·폴더 (15) | 2 — 코어는 SQLite만. `--crossdb`는 처음 10개만 ATTACH | 2 — 연결 문자열 여러 개 ATTACH. CSV·Excel은 DuckDB SQL로 직접 |
| C3 한글 (10) | 3 — 테이블명 틸드 인코딩, 비ASCII 테스트 있음. 단 경로를 이스케이프 없이 `file:` URI에 넣음 → 아래 실측 | 3 — `Path.as_uri()` 사용(안전) ✔. ATTACH 별칭을 인용 없이 씀 |
| C4 대용량 (10) | 5 — 페이지 100행, 최대 1000행, 쿼리 1000ms 제한, `fetchmany`, CSV 스트리밍 | 4 — `--limit` 하드 한도와 뷰어 소프트 한도 |
| C5 에이전트 제어 (15) | 5 — 모든 화면이 `.json`, 서버 없이 `--get`, 고정 오류 봉투 | 4 — 헤드리스 `hsql`(csv/json/jsonl), 종료 코드 규약, 에이전트용 SKILL.md 출력 |
| C6 비SQL 탐색 (10) | 4 — 패싯, 필터(exact/contains/in/gte…), FTS(테이블 있을 때만) | 1 — SQL 편집기 중심, 이름 검색뿐 |
| C7 재사용성 (10) | 4 — pluggy 훅 약 40개, `Database` 클래스 재사용 가능. `app.py` 3500줄 덩어리 | 3 — 어댑터 ABC와 `IMPLEMENTS_*` 기능 선언. TUI 전용 |
| C8 설치 용이성 (5) | 4 — PyPI, 순수 Python 위주 | 4 — PyPI, 단 의존성 정확 고정으로 충돌 가능 |
| **합계 /100** | **77** | **54** |

## 메인 실측: `file:` URI 경로 이스케이프 (scratchpad probe, Python sqlite3)

| 파일명 | Datasette식 `file:{path}?mode=ro` | `Path(p).as_uri() + '?mode=ro'` |
|---|---|---|
| `한글 공백.sqlite` | OK | OK |
| `예산#2026.sqlite` | **오류 "no such table" + 원본 폴더에 빈 파일 `예산` 생성** | OK |
| `50%할인.sqlite` | OK(우연. `%할`이 유효한 퍼센트 이스케이프가 아님) | OK |
| `plain.sqlite` | OK | OK |

원인: `#` 뒤가 URI fragment로 잘리면서 `?mode=ro`도 같이 사라져 기본 모드(rwc)로 다른 경로를 열고 생성.
**ldx 규칙: SQLite URI는 반드시 `Path(...).as_uri()`로 만들고, 연결 후 `PRAGMA query_only=1`을 이중 장치로 건다.**
→ W3 원본 불변 속성에 "원본 폴더에 새 파일이 생기지 않는다"를 추가할 것.

## ldx에 가져올 것

아키텍처
- Datasette: 읽기 연결 분기(`mode=ro` 대 `immutable=1`), 쓰기 연결 assert, 기본 거부 권한 목록, JSON 오류 봉투 `{"ok":false,"error","errors","status"}`, 서버 없이 같은 앱을 부르는 `--get`
- Datasette: SQLite authorizer로 쓰기 문장 검출(`utils/sql_analysis.py:204-247`) — DuckDB `json_serialize_sql` 검사와 이중화 후보
- Harlequin: 어댑터 계약(`execute`, `cancel`, `get_catalog`, `search_catalog`)과 `IMPLEMENTS_READ_ONLY` 같은 기능 선언, 선언 없는 어댑터에 `--read-only` 거부
- Harlequin `hsql`: 엔진/클라이언트 분리, CLI가 에이전트용 SKILL.md를 출력

기능
- 시간 제한 + 행 수 제한 자르기, 키 기반 페이징, CSV 스트리밍 (Datasette)
- 패싯과 비SQL 필터 UI (Datasette)
- 쿼리 취소(`conn.interrupt()`)와 타임아웃 종료 코드 (Harlequin)
- 카탈로그 이름 검색을 `pragma_table_info`로 한 번에 (Harlequin)

## 한계
- Datasette `immutable=1`은 실행 중 원본이 바뀌면 오래된 결과를 보일 수 있음(문서 명시)
- Windows에서 두 도구를 실제로 실행하지는 않음(경로 실측은 Python sqlite3로 동일 URI만 재현)
