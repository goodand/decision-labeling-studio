# 벤치마킹 종합 (2026-11-02, 기준 v1)

기준과 가중치: [criteria.md](criteria.md). 점수 = Σ(점수/5 × 가중치). 상세 근거는 회차별 문서.

## 채점 대상 (같은 기준표)

| 순위 | 후보 | C1 불변 25 | C2 파일 15 | C3 한글 10 | C4 대용량 10 | C5 에이전트 15 | C6 탐색 10 | C7 재사용 10 | C8 설치 5 | 합계 | 근거 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Datasette | 4 | 2 | 3 | 5 | 5 | 4 | 4 | 4 | **77** | [round2_datasette_harlequin](round2_datasette_harlequin.md) |
| 2 | Rill | 3 | 3 | 3 | 2 | 4 | 4 | 3 | 1 | **61** | [round2_evidence_rill_duckdbui](round2_evidence_rill_duckdbui.md) |
| 3 | KNIME | 2 | 4 | 3 | 4 | 3 | 4 | 2 | 3 | **60** | [round2_powerbi_knime](round2_powerbi_knime.md) |
| 3 | DuckLocal | 3 | 3 | 3 | 3 | 4 | 3 | 2 | 2 | **60** | 공유 노트 ldx_oss_benchmark (재채점) |
| 5 | Power BI Desktop | 3 | 4 | 4 | 2 | 2 | 4 | 1 | 4 | **59** | [round2_powerbi_knime](round2_powerbi_knime.md) |
| 6 | Harlequin | 2 | 2 | 3 | 4 | 4 | 1 | 3 | 4 | **54** | [round2_datasette_harlequin](round2_datasette_harlequin.md) |
| 7 | Octa | 1 | 4 | 2 | 1 | 4 | 4 | 2 | 2 | **49** | 공유 노트 ldx_oss_benchmark (재채점) |
| 8 | DuckDB UI | 2 | 3 | 3 | 4 | 2 | 0 | 3 | 3 | **48** | [round2_evidence_rill_duckdbui](round2_evidence_rill_duckdbui.md) |
| 9 | Evidence | 2 | 1 | 0 | 0 | 3 | 1 | 3 | 1 | **31** | [round2_evidence_rill_duckdbui](round2_evidence_rill_duckdbui.md) |

1차 후보 재채점 근거
- DuckLocal: C1 DB 파일 기본 읽기 전용·`.dash` SELECT 검사 있으나 CLI `query`는 `COPY`로 파일 쓰기 가능(`src/cli.rs:43`). C2 폴더 확장·Excel은 GUI만(`src/schema_cli.rs:359-374`). C3 한글 경로·시트 보존, `.dash` 식별자 ASCII만. C4 CLI 1000행 기본·셀 상한, Excel은 전체 적재. C5 JSON·종료 코드·SKILL. C7 lib 타깃 없음·spec→gpui 의존. C8 바이너리가 GitHub 릴리스(이 PC 차단), 소스 빌드는 Rust+C++.
- Octa: C1 저장 시 SQLite를 읽기·쓰기로 열고, `--mcp-read-only`에서도 `run_sql` 원시 SQL이 그대로 실행(`src/mcp/tools/run_sql.rs:271`, `src/sql/workspace/session.rs:356-368`). C3 비ASCII 이름을 `_`로 바꿈(`src/sql/workspace/mod.rs:656-676`), CSV UTF-8 전제. C4 SQLite 테이블 전체 적재(`src/formats/sqlite_reader.rs:199-211`). C8 바이너리가 GitHub 릴리스(차단).

## 채점하지 않은 참고 대상
| 대상 | 이유 | 쓰는 방식 |
|---|---|---|
| REA | 데이터 도구가 아님(역공학 MCP) | 아키텍처만: 계약 하나→CLI·MCP, 효과 플래그→읽기 전용 표시, Evidence 봉투, 에러 분류 |
| Dataloupe | 화면만 봄, 단일 파일 뷰어 | 기능만: 열 카드 + 그리드 + 전체 검색 |
| DBML ERD Viewer | ERD 컴포넌트 | 기능만: PK/FK 배지, 실선·점선 |
| Duck-UI | 코드 미검토, 화면 1장 | 참고만: SQL 워크벤치 화면 |
| Docling | 사용자 결정으로 제외 | 문서 파싱은 govparse MCP |

## 결론
1. 그대로 채택할 후보는 없다. 1위 Datasette(77)도 CSV·Excel을 직접 다루지 못한다(C2=2).
2. 원본 불변(C1)에서 5점은 없다. 가장 높은 Datasette(4)도 `#` 포함 경로에서 URI가 잘려 원본 폴더에 새 파일을 만드는 것을 실측(round2_datasette_harlequin). ldx는 C1=5를 목표로 W3 설계 검증부터 한다.
3. 가져올 것은 회차별 문서의 "ldx에 가져올 것"에 있고, Subflow별로 `subflows.yaml`에 반영한다.
4. 사람용 보조 화면은 이 PC에서 지금 바로 쓸 수 있는 것: Datasette(PyPI, 읽기 전용 `-i`), DuckDB UI(`duckdb -ui`, 온라인 필요).
