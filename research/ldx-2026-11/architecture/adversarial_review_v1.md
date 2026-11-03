# 다이어그램 v1 적대 검증 판정표 (2026-11-02)

대상: architecture.png · runtime_workflow.png · dev_workflow.png (커밋 f70db15)
검증자: opus 서브에이전트 3명 — A 원본 불변 공격 / B 아키텍처 정합성 / C 워크플로 실행성. 각자 이미지를 Read한 뒤 문서·코드·합성 파일 실험으로 근거 제시.
메인 재현: ✔ = 메인이 직접 재현(scratchpad probe, 합성 파일), ◐ = 코드·문서로 확인, — = 미재현.
결정: 반영 / 보류(사유) / 기각(사유). 반영은 다이어그램 v2·README·subflows.yaml·dependencies.md에 일괄 적용 예정(순서 변경 승인 후).

| ID | 출처 | 심각도 | 지적 | 메인 재현 | 결정 |
|---|---|---|---|---|---|
| R01 | A1·C1 | 치명 | WAL 모드 SQLite를 `mode=ro` 또는 DuckDB `READ_ONLY ATTACH`로 열면 원본 옆에 `-shm`·`-wal` 생성, 닫은 뒤에도 남음. `immutable=1`은 생성 없음 | ✔ (wal_test: mode=ro·ATTACH 모두 생성, immutable=1 없음) | 반영: 헤더 18~19바이트로 WAL 판별 → WAL이면 `.ldx/snapshots/`에 DB+WAL 복사본을 열고, 아니면 기존 경로. dependencies.md의 "-wal/-shm 미생성"은 비WAL 사본 실측이었음을 정정 |
| R02 | A2 | 치명 | DuckDB sqlite 확장은 URI를 받지 않아 `immutable=1` 불가 | ✔ (as_uri·일반 경로 둘 다 "Unable to open database") | 반영: DuckDB 조회 경로에서 WAL 원본은 항상 스냅샷만 ATTACH |
| R03 | A3 | 높음 | `WITH d AS (DELETE … RETURNING *) SELECT …`가 `json_serialize_sql` 검사를 통과하고 실제 실행 | ✔ (gate ALLOWED, 테이블 5행→0행) | 반영: 쿼리 연결은 별도 in-memory, 카탈로그는 READ_ONLY ATTACH만, 직렬화 트리에서 CTE 내부 문장 종류까지 검사 |
| R04 | A4 | 높음 | DuckDB `temp_directory` 기본값이 상대경로 `.tmp`(cwd 기준) → 원본 폴더가 cwd면 spill 파일·빈 `.tmp/` 생성 | ◐ (기본값 `('.tmp',)` 확인. spill 생성은 메인 실험에서 OOM이 먼저 나 미재현, A는 재현) | 반영: 모든 연결을 팩토리 하나로, 첫 줄에 절대경로 `temp_directory`·`max_temp_directory_size`. `.ldx` 등 모든 경로는 패키지 위치 기준 |
| R05 | A5·B4·C7 | 높음 | 게이트 통과 SELECT 안의 `read_csv`·`FROM '경로'`·`sqlite_scan`·`glob` 등으로 등록 안 된 파일 접근, autoinstall로 네트워크 접근 가능 | ✔ (read_csv·FROM 'x.csv' ALLOWED. `enable_external_access=false`+`lock_configuration=true` 후 차단, 붙인 SQLite 뷰는 정상, 재설정 거부) | 반영: 순서 고정 — 스냅샷 ATTACH → temp_directory → enable_external_access=false → autoinstall/autoload off → lock_configuration=true |
| R06 | C7 | 중간 | 다중 SELECT(`select 1; select 2`) 통과 | ✔ | 반영: 문장 수 = 1 검사 |
| R07 | B1·C2 | 치명 | GUI가 `catalog.duckdb`를 쓰기로 열면 CLI는 읽기 전용으로도 못 엶 | ✔ (IO Error, read_only=True도 실패) | 반영: 명령마다 짧게 연결·즉시 닫기, 잠김은 오류 종류 `catalog_busy` + 고정 종료 코드, doctor에 잠금 점검 |
| R08 | B2 | 높음 | 2차 검사 "SQLite authorizer"는 Python sqlite3 전용이라 DuckDB 실행 경로에 효과 없음 | ◐ (API 성격상 자명) | 반영: authorizer 제거, DuckDB 전용 장치(R03·R05·R06)로 대체 |
| R09 | B3·C3 | 높음 | "adapters 밖 connect 엣지 0" 관문은 지킬 수 없음(core도 카탈로그 연결 필요) + graphify는 별칭 import·`duckdb.sql()`을 구별 못함 | ◐ (C의 gproj 실험 근거 확인) | 반영: 연결 소유 모듈 `ldx/engine.py` 신설, 관문은 pytest AST 검사로("원본 ATTACH·파일 열기는 adapters만", core에서 web/cli import 금지). graphify는 시각화·참고용 |
| R10 | B4 | 높음 | 조회 경로 ⑬이 adapters를 거치지 않고 직접 ATTACH | ◐ | 반영: ATTACH는 adapters가 제공, query는 등록된 뷰만 사용 |
| R11 | B5 | 높음 | 사후 검사 "원본 해시 불변"이 정상적인 외부 수정과 충돌, 기준 해시 저장 위치 없음 | ◐ | 반영: 해시 불변은 테스트(사본)에서만. 런타임은 명령 전후 원본 폴더 목록·부속 파일 비교(A9 반영) |
| R12 | A6 | 높음 | sha256·sqlite3·calamine 객체가 핸들을 쥔 동안 사용자 Excel 저장(교체)이 PermissionError | — (A 재현) | 반영: 공유 모드 열기, calamine은 bytes로 읽기, 핸들 즉시 닫기, 교체 감지 시 재시도 |
| R13 | A7 | 중간 | 정션을 따라가면 `.ldx`가 원본 폴더 안에 있는지 검사가 뚫림 | — (A 재현) | 반영: 정션·심볼릭 링크는 들어가지 않고 limitations에 기록 |
| R14 | C5 | 높음 | 잠긴 파일, mtime을 되돌린 변경 감지 누락 | — (C 재현) | 반영: `locked` 상태, 파싱 전후 해시 비교, `st_mtime_ns`, 강제 재해시 옵션 |
| R15 | C6 | 중간 | `{파일}_{시트}` 이름 충돌(구분자 모호·폴더 간 동명·대소문자) | — (C 재현) | 반영: 내부 ID = 상대경로+시트 해시, 표시 이름 별도, 충돌 시 접미사+경고 |
| R16 | C8 | 중간 | 잘못된 바이트 1개로 CSV 전체 손실, 0바이트 CSV가 정상 표와 구별 안 됨 | — (C 재현) | 반영: 행 단위 거부 기록, `empty` limitation |
| R17 | C9 | 중간 | Fuzzy 0점 결과가 RRF로 1위 가능, Kiwi가 코드·숫자를 쪼갬 | — (C 재현) | 반영: score_cutoff, 원문 토큰·n-gram 병행, 코드·숫자 골든 테스트 |
| R18 | C10 | 중간 | 처음 1,000행 프로파일·approx_unique가 오해 유발 | — (C 재현) | 반영: 표본·근사 표시, unique는 정확 계산 |
| R19 | C4 | 높음 | W3 대상 "원본 불변"은 순차 성질이라 TLA+에 부적합 | ◐ (formal-verify SKILL.md 용도 설명 확인) | 반영: W3 대상을 "카탈로그 최신성"(스캔 중 변경, GUI·CLI 동시 갱신, 중단)으로. 원본 불변은 테스트로 |
| R20 | C11·B7 | 중간 | 단계 순서·상태 표시 모순(시나리오 미착수인데 벤치마킹 완료), 관문 측정 불가 | ◐ | 반영: 순서를 수용 테스트→설계→설계 검증→명세 테스트→코드로(사용자 승인 대기), ④ 관문에 변이 테스트·재구현 훈련, ⑦ 산출물 = 이 판정표 |
| R21 | B6 | 중간 | contracts가 core 안인데 그림은 위층, adapters가 봉투 타입 import 시 순환 | ◐ | 반영: `ldx/types.py`(의존 없음) 분리, 명령 계약은 interfaces 바로 아래 |
| R22 | B8·B11 | 중간 | README "FastAPI 얇게"가 "화면 기술 미정"과 충돌, profile.py 누락, `ok` 필드·오류 형식 2종, openpyxl 실행 의존성, `.ldx/` gitignore 누락 | ◐ | 반영 |
| R23 | B9 | 중간 | 색인 범위 미정(셀 전체 색인 시 2GB 부담) | — | 보류: 사용 시나리오(1단계) 후 결정 |
| R24 | B11·C12 | 중간 | `D:\dev_eval_team` 등록이 "원본 안이면 거부" 규칙에 막힘(ldx_workbench가 그 하위) | ◐ (경로 관계 자명) | 반영: 거부 대신 `.ldx`를 스캔에서 제외 |
| R25 | A11 | 낮음 | `writes_source` 플래그는 자기 신고라 강제력 없음 | — | 반영: R09 AST 검사가 실제 강제 장치 |
| R26 | A10 | 중간 | 다른 프로그램이 쓰는 WAL DB를 오래 읽으면 체크포인트 방해 | — | 반영(R01 스냅샷으로 해결) |
| R27 | C12 | 낮음 | sqlite 확장은 실행 중 INSTALL(uv.lock 밖), tlc.sh PATH 점검 단계 없음 | ◐ | 반영: doctor가 확장 버전·Java PATH 점검 |

## 버틴 장치 (A가 깨려다 실패)
핫 저널은 `mode=ro`·ATTACH·sqlite_scan 모두 거부, `json_serialize_sql`은 COPY·ATTACH·SET·PRAGMA·CALL·INSTALL·LOAD·EXPORT·CREATE TEMP AS 거부, READ_ONLY ATTACH는 SQLite DELETE 차단, lock 후 SET 차단, `as_uri`는 `#`를 `%23`으로 안전 처리.

## 메인 판단
- 원본 불변 목표(C1=5)를 막는 실제 구멍은 R01·R02·R03·R04·R05로, 모두 v1 그림에 없던 것.
- 현재 실제 대상 DB 5개는 모두 WAL이 아님(헤더 확인) → 당장의 원본 손상 위험은 낮지만 설계는 WAL을 기본 전제로 고친다.
