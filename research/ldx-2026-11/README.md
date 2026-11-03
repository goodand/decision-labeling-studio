# ldx 리서치 보관 색인 (브랜치 `research/ldx-2026-11-03`)

2026-11-02~03 동안의 벤치마킹·설계·검증·실측 자료를 한 브랜치에 보관한다. 파일은 원래 위치 그대로 두었다(용어 검증 스크립트가 `docs/glossary` 경로를 직접 읽기 때문). 이 색인만 읽으면 무엇이 어디 있고 무엇이 결론인지 알 수 있게 정리했다.

## 1. 최종 결론 (먼저 읽기)
- **역할 분담:** 대부분의 로직(질의 정규화, 대조 규칙, 검색 전략)은 에이전트가 직접 만든다. 도구는 사람이 원하는 GUI와 호환되는 데 집중한다. → `docs/scenarios.md` "역할 분담"
- **사람 GUI:** 엑셀(보기·편집, 관계형 DB 보기에는 불편)과 decision-labeling-studio(판정 검수). GUI 기준 채점 studio 82 · 엑셀 63 · KNIME 55 · Datasette 49 · Dataloupe 44 · DuckDB UI 43, Power BI 보류. → `docs/benchmarking/gui_criteria_v2.md`
- **저장소 구조(사용자 결정):** DB 백엔드 + DB를 보는 로컬 GUI를 **새 저장소 하나**로. 판정 검수 화면은 decision-labeling-studio 몫. 이름은 별도 세션에서 검증 중(`docs/glossary/repo_names*.yaml/md`, master 쪽).
- **DB GUI 화면 기준:** Airtable 화면을 참조(클라우드 아님). 기본 보기 "사업 1행 × 소스별 열"(연결 레코드 + lookup), 연결 칩·카드, 레코드 펼쳐 보기, 딥링크. → `docs/benchmarking/airtable_relational_ui.md`
- **최소 구성에서 뺀 것:** Kiwi 형태소 색인(실제 검색 2건이 Kiwi 없이 찾아짐), 자체 서버 재시작·배너 플러그인(설계 v3.2), 웹 대조 canned query.
- **반드시 지킬 것(실측 근거):** 원본은 공유 옵션 READ·WRITE·DELETE로만 열기(일반 open은 다른 프로그램 COMMIT을 실패시킴, Z1), 부속 파일 이름 맞춤 복사(Y1/F1), 사본은 `mode=ro&immutable=1`(Y7), 쿼리 가드는 sqlite3 authorizer(E2/F2).

## 2. 시간순 흐름 (커밋)
| 단계 | 커밋 | 내용 |
|---|---|---|
| 착수·벤치마킹 1~2차 | eaa0b0e, c6e27b7 | 기준 C1~C8, 9개 후보 채점(Datasette 77 1위, v1 기준) |
| 다이어그램 v1·v2 | f70db15, 41c8320, 7fd6e32 | 판정표 R01~R27, S01~S20 |
| 용어 검증 | 311bf83, 9e8f79b | 18개 확정, 모델 다각화 |
| 시나리오 v2·v3 | 75f74bf, 6a6a4cd, 31f32cb~4004c3c | 세션 기록 빈도, 색인 범위 R23, 기능별 최소 구성·재사용 |
| Datasette 실측 | 22472e9, f5bcfd4 | WAL·`#` 경로 조용한 누락 |
| 설계 v3 → v3.1 → v3.2 | 57aa09d … ecd7e2a | 적대 검증 3회(X·Y·Z), 실측 E1~E5·F1~F4 |
| 이름 검증 | dba99c0, 7d5aec5 | 로컬 Qwen + gpt-6-luna 격리, 하위 에이전트 맥락 오염 실측 |
| 방향 전환 | 60b3160 | 로직은 에이전트, ldx는 GUI 호환 |
| GUI 벤치마킹 v2 | 41cbc9c, ad0fbb2 | 사용자 UI 결정 로그 기준 재채점, KNIME·DuckDB UI 실측 |
| Airtable | ebed713, 836133c | 공개 미리보기 + REA 구조, 로그인 계정에서 합성 2소스 대조 재현 |

## 3. 폴더별 안내
### 벤치마킹 `docs/benchmarking/`
| 파일 | 내용 |
|---|---|
| `criteria.md`, `summary.md`, `round2_*.md` | v1 기준(에이전트·원본 불변 중심) 채점. **GUI 관점으로는 대체됨** |
| `datasette_fit_2026-11-03.md` | Datasette 재사용 실측(WAL·`#`·FTS 없는 표 조용한 오답) |
| `gui_criteria_v2.md` | **GUI 관점 v2 기준과 채점(현행)** |
| `airtable_relational_ui.md` | **Airtable 화면 패턴, REA 관찰, 합성 재현(현행)** |
| `gui_shots/` | 화면 증거 11장(studio, Dataloupe, DuckDB UI, KNIME, Airtable) |

### 설계·적대 검증 `docs/architecture/`
| 파일 | 내용 |
|---|---|
| `architecture.*`, `runtime_workflow.*`, `dev_workflow.*` | v1·v2 그림 |
| `architecture_v3*.{html,png}`, `runtime_v3*.{html,png}` | v3, v3.1, v3.2 그림 |
| `adversarial_review_v1.md` ~ `_v3_2.md` | 판정표(R·S·X·Y·Z) + 실측 결과. v3.2가 최신 |
| 주의 | v3.x의 서버·배너·Kiwi 부분은 방향 전환(60b3160)·GUI v2 결론으로 최소 구성에서 빠짐. **원본 불변 부분(Z1·Y1·Y7 등)은 새 저장소에도 그대로 유효** |

### 용어·이름 `docs/glossary/`
| 파일 | 내용 |
|---|---|
| `GLOSSARY.md`, `terms.yaml`, `final_terms.json`, `rounds/` | 18개 용어 검증 |
| `names.yaml`, `names_r2.yaml`, `names_results.md`, `names_rounds/` | 코드 이름 22개 검증(read_ratio, positions_only 등 교체 결정) |

### 실측 스크립트 `scripts/`
| 파일 | 내용 |
|---|---|
| `check_terms.py`, `ask_local_llm.py`, `term_validation_loop.workflow.js` | 용어·이름 검증 하네스 |
| `evidence/classify_sc.py`, `mine_session.py`, `measure_text.py` | 세션 기록 분류, 텍스트 규모 측정 |
| `evidence/probe_ds.py`, `probe_xlsx_fts.py` | Datasette·엑셀 FTS 실측 |
| `evidence/exp_v3.py`, `exp_e5.py`, `exp_v31.py`, `exp_f4.py` | 대책 실측 E1~E5, F1~F4 |

### 기타
- `docs/scenarios.md`: 시나리오 SC1~SC7, 수용 속성 A01~A17, 역할 분담, 기능별 최소 구성
- `docs/dependencies.md`, `README.md`, `subflows.yaml`: 초기 결정(일부 낡음, 판정표 S18 참고)

## 4. 저장소 밖 자료(이 브랜치에 없음)
- 실험 원본 결과: `%TEMP%\ldxg\`(KNIME·REA·Edge 프로필), 세션 scratchpad `dsprobe\`, `guitools\` — 저장소 센스가 지울 수 있음
- 격리 실행기: `D:\web_chat_gpt\workflow-runner\adapters.py`(OMP), `claude_adapter.py`(Claude)
- Airtable 베이스 "Product catalog"(사용자 계정, 합성 데이터)
