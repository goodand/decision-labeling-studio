# 2차 벤치마킹: Evidence, Rill, DuckDB UI (코드 읽기 + 메인 확인)

기준: [criteria.md](criteria.md) v1. 코드 평가: sonnet 서브에이전트. ✔ = 메인 직접 확인.

| 기준 (가중치) | Rill (451a57c, Apache-2.0) | DuckDB UI (b4f0b9b, MIT·화면 비공개) | Evidence (590143b, MIT) |
|---|---|---|---|
| C1 원본 불변 (25) | 3 — 외부 DB는 `ATTACH … (READ_ONLY)`, 조회 SQL은 `SELECT * FROM (…) LIMIT`로 감쌈. 관리형 DuckDB는 쓰기 기본, 모델 `pre_exec`는 임의 SQL | 2 — `/ddb/run`이 받은 문장을 그대로 실행(쓰기·ATTACH·COPY 차단 없음) | 2 — 로컬 원본을 여는 경로 자체가 없음 |
| C2 로컬 파일·폴더 (15) | 3 — `local_file` 커넥터, SQLite는 `sqlite_scan()`, Excel 입력 미지원 | 3 — 엔진(DuckDB) 수준으로 CSV·SQLite·글롭·JOIN | 1 — 플랫 파일은 클라우드 업로드 방식 |
| C3 한글 (10) | 3 — CSV 옵션을 `read_csv_auto`에 그대로 전달 | 3 — DuckDB 엔진 의존 | 0 — 근거 없음 |
| C4 대용량 (10) | 2 — 소스를 DuckDB 테이블로 복사 적재(2GB를 한 번 더) | 4 — 엔진 지연 스캔, 행 한도 헤더(기본 무제한) | 0 — 서버측 실행 |
| C5 에이전트 제어 (15) | 4 — `rill query --local --sql`, gRPC, MCP 서버(서버 기동 필요) | 2 — localhost HTTP, 이진 응답, CLI·JSON 규약 없음 | 3 — `evidence query --format json`, 단 로그인 필수 |
| C6 비SQL 탐색 (10) | 4 — 컬럼 프로파일, 차원 값 검색, 필터 | 0 — 화면 비공개라 확인 못함 | 1 — 리포트 제작 도구 |
| C7 재사용성 (10) | 3 — Go 런타임·protobuf·Svelte 분리, 단 CGO 단일체 | 3 — 확장과 TS 패키지 일부만 공개 | 3 — 코어 private 패키지 |
| C8 설치 용이성 (5) | 1 — Windows 바이너리 없음 ✔ (`.goreleaser.yaml` goos: linux, darwin) | 3 — 확장은 extensions.duckdb.org, 화면은 실행 때마다 `https://ui.duckdb.org`에서 받음 ✔ (`src/include/settings.hpp:8`). 이 PC에서 연결됨(200) ✔, 오프라인 불가 | 1 — `irm … \| iex` 설치 + 로그인 |
| **합계 /100** | **61** | **48** | **31** |

## 판단
- Evidence: 현재 저장소는 클라우드형 "Evidence Studio"라 로컬 파일 도구가 아님 → 후보 제외(CLI 출력 옵션만 참고)
- DuckDB UI: 화면 코드가 비공개이고 원격 의존 → 코드 재사용 대상 아님. 사람용 보조 SQL 화면으로는 이 PC에서 지금 바로 쓸 수 있음(`duckdb -ui`)
- Rill: Windows 미지원·소스 복사 적재로 채택 불가. 구조와 프로파일 기능만 참고

## ldx에 가져올 것
아키텍처
- Rill 리소스 reconciler: 파일로 정의한 리소스를 DAG 순서로 재조정(`runtime/reconcilers/README.md`) → 카탈로그 증분 갱신 설계 참고
- Rill 드라이버 인터페이스 분리(OLAPStore, FileStore) → adapters 경계 참고
- DuckDB UI: localhost 한정 + Origin 검사(`src/http_server.cpp:404-408`) → ldx web 서버 기본값
- Evidence: 쿼리 실행 계층을 인터페이스로 주입(`core/src/user-components/interfaces/query-service.ts`)

기능
- Rill 컬럼 프로파일 쿼리: NullCount, NumericHistogram(`runtime/server/queries_columns.go`)
- Rill CSV 샘플링 기본값 `sample_size=200000`, 대화형 SQL 행 한도
- Evidence CLI: `--columns`(이름·타입만), `--format json|jsonl|csv|table`, `--limit`, `-`로 stdin 입력
- DuckDB UI: 큰 결과를 임시 테이블에 두고 페이지로 가져오기(`Result-Table-*` 헤더)

## 한계
- Rill 작업 트리가 불완전하게 풀려(Windows 경로 문제 추정) 근거를 `git show HEAD:경로`로 읽음
