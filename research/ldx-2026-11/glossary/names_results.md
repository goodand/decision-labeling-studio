# 이름(식별자) 검증 결과 (2026-11-03)

방법: GLOSSARY 용어 검증과 같음. 이름만 주고 설명 → names.yaml 규칙 판정 → 메인이 설명문 직접 읽어 교차 확인 → 실패 이름은 후보로 재검증.
기준 모델: 로컬 Qwen(qwen/qwen3.8-27b, 프롬프트에 이름 목록만). Claude 하위 에이전트 표본은 맥락 유입으로 참고용(아래 격리 실측).

## 1회차 (22개 이름)
- 규칙·직접 읽기 모두 통과: scan, source add, show, export, ok, truncated, total_rows, total_rows_exact, limitations, mtime_ns, locked, sql_rejected, catalog_busy, catalog, types.py
- 오해: compare(차이 계산으로 읽힘), location_only(내용을 아직 못 읽은 "상태"로 읽힘 — 의도는 원문 제거 옵션), read_completeness(비율이 아닌 예/아니오), .ldx/data(사본이라는 뜻 없음), _행(행 수·행 자체로 읽힘), status(무엇의 상태인지 모름), data(Qwen 1/3 일반 데이터)

## 2회차 후보 (로컬 Qwen 3표본)
| 원래 | 후보 | 결과 | 판단 |
|---|---|---|---|
| read_completeness | read_ratio / files_read_ratio | 3/3 / 3/3 | **read_ratio** |
| .ldx/data | .ldx/copies / .ldx/snapshots / .ldx/source_copies | 각 3/3 | **.ldx/copies** (가장 짧고 쉬움) |
| status | read_status | 3/3 | **read_status** |
| _행 | _source_row / 원본_행번호 / _행번호 | 각 3/3 | **_source_row** (영문 열 이름과 일관) |
| location_only | positions_only | 규칙 0/3 → v1.2 규칙·직접 읽기 3/3 | **positions_only** |
| location_only | hide_cell_text / omit_cell_values | 0/3 | 위치 반환 뜻 없음, 탈락 |
| compare | side_by_side / compare_side_by_side | 2/3 / 1/3 (v1.1 규칙) | 명령 이름은 `compare` 유지, 도움말 첫 줄에 "나란히, 합치지 않음". v1.2 규칙으로 재판정 필요 |

## Claude 하위 에이전트 맥락 격리 실측 (workflow, 6 에이전트)
| 유형 | 모델 | 보이는 맥락(자가 보고) | 설명 오염 |
|---|---|---|---|
| 기본 | haiku | 메모리(ldx 워크벤치 MVP), 작업 경로 | 있음 |
| 기본 | sonnet | CLAUDE.md, MEMORY.md, 작업 경로 | 있음 |
| Explore | haiku·sonnet | 작업 경로(ldx_workbench), 스킬 목록 | 경로 수준만 |
| Plan | haiku·sonnet | 작업 경로, 하네스 지시 | 경로 수준만 |

결론: Explore·Plan 유형은 CLAUDE.md·메모리를 빼지만 작업 디렉터리 경로는 남는다(완전 격리 아님). 이름에 프로젝트 고유 단어(`ldx`)가 있으면 경로에서 힌트를 얻는다. 절차: Claude 표본은 Explore/Plan 유형 + 고유 단어 가리기(예: `.ldx/` → `.app/`), 완전 격리 기준은 로컬 LLM.

## 완전 격리 표본: Codex 세션이 만든 OMP 실행기 (2026-11-03)
도구: `D:\web_chat_gpt\workflow-runner\adapters.py`의 `run_agent`를 수정 없이 import (Codex 세션 01a12fb7가 작성). 매 호출 새 OMP 프로세스·세션, `--no-tools --no-extensions --no-skills --no-rules`, 별도 작업 폴더·정리된 환경변수, 시작 시 메시지 0개·도구 0개·고정 시스템 프롬프트를 확인하고 어긋나면 실패. 모델 gpt-6-luna(추론 medium) — 모델 계열도 다각화.
- 맥락 탐침: "ldx 또는 workbench 관련 정보는 없음", 도구 `[]`. 보이는 것은 실행기 자신의 작업 폴더 이름뿐 → 작업 폴더 이름에 프로젝트 단어를 쓰지 않으면 된다.
- 1회차(22개, 1표본): 실패 compare·read_completeness·status·location_only·_행·.ldx/data — 로컬 Qwen과 **같은 6개**.
- 2회차 후보(2표본, v1.2 규칙): side_by_side 2/2, read_ratio 2/2, positions_only 2/2, .ldx/copies 2/2, read_status 2/2, _source_row 2/2. hide_cell_text·omit_cell_values 0/2 — 로컬 Qwen과 **같은 결론**.
- 결론: 독립된 두 모델(로컬 Qwen, gpt-6-luna)이 같은 이름을 오해하고 같은 후보를 통과시켰다. 이름 교체 확정 근거로 쓴다.
