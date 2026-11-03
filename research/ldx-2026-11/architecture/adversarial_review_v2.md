# 다이어그램 v2 적대 검증 판정표 (2026-11-02)

대상: v2 PNG 3장(커밋 41c8320). 검증자: opus 3명 — A 원본 불변 / B 아키텍처·문서 정합성 / C 워크플로 실행성.
메인 재현: ✔ 직접 재현(scratchpad 합성 파일), ◐ 문서·코드로 확인, — 미재현.

## 새 지적

| ID | 출처 | 심각도 | 지적 | 메인 재현 | 결정 |
|---|---|---|---|---|---|
| S01 | A1 | 치명 | 헤더는 비WAL인데 `-wal`이 남은 DB를 v2 경로(`mode=ro`)로 열면 원본 폴더에 `-shm` 생성 | ✔ (`r.sqlite-shm` 생성, `immutable=1`은 생성 없음) | 반영: 판별 = 헤더 2 **또는** `-wal/-shm/-journal` 존재 → 스냅샷. 비WAL도 sqlite3는 `immutable=1`로. DuckDB 경로는 URI 불가(R02)라 원본 직접 ATTACH 금지, 항상 스냅샷 |
| S02 | A3 | 높음 | ATTACH 경로를 문자열로 끼워 넣으면 `'` 포함 경로에서 파싱 오류, 옵션 조작 여지 | ✔ (f-string 오류, `ATTACH ? AS …` 바인딩 정상) | 반영: 명세는 구조체(path, alias, type), 실행은 바인딩, alias는 `[A-Za-z0-9_]`, AST 검사에 "ATTACH f-string 금지" |
| S03 | A4 | 높음 | 설정 순서에서 ATTACH가 temp_directory·autoinstall 끄기보다 먼저 | ◐ (temp 기본값 `.tmp` 재확인됨) | 반영: temp_directory → autoinstall/autoload 끄기 → 확장 LOAD → ATTACH → external_access=false → lock. 시작 시 cwd를 `.ldx/tmp`로 |
| S04 | B1 | 치명 | "ATTACH는 adapters만" 관문이 실제 실행자인 engine을 막음 | ◐ | 반영: adapters = 명세 생성, engine = 유일 실행자. 관문 = "connect·ATTACH 호출은 engine만, 원본 경로 명세는 adapters만" |
| S05 | C7 | 중간 | mutmut은 Windows 미지원 | ✔ (mutmut 3.8.1: "To run mutmut on Windows, please use the WSL") | 반영: ⑤ 관문 도구를 교체 — 후보 cosmic-ray(실측 필요) 또는 자체 AST 변이(비교 연산자·가드 삭제) + pytest |
| S06 | C1·B10 | 높음 | 승인 순서(수용 테스트 → 설계) 위반: ① 미착수인데 ③ 초안·④ 진행 중 | ◐ | 반영: ③은 "참고 초안(① 이후 재작성)", ④는 ① 완료까지 보류. 다음 작업 = ① 시나리오·수용 테스트 |
| S07 | C2 | 높음 | 정형 설계 검증 대상의 속성 미정의 | ◐ | 반영(①에서 고정): P1 NoStaleClean, P2 NoLostUpdate(GUI·CLI 동시 갱신), P3 활성(변경은 결국 갱신 또는 locked) |
| S08 | A2·C3 | 높음 | 판별→복사→열기 경쟁, 쓰는 중 WAL DB 스냅샷 시점 불일치 | — | 반영: 복사 전후 (size, mtime_ns, 헤더 change counter 24~27바이트, wal size) 비교·재시도, 사본은 `immutable=1` |
| S09 | C4·B12 | 중간 | 스냅샷 캐시 무효화 키·보관 개수·디스크 상한 없음 | — | 반영: 키 = (경로, size, mtime_ns, wal size, wal mtime_ns), 최신 1개, `max_snapshot_bytes`, 부족 시 limitation |
| S10 | C5 | 중간 | `read_completeness` 정의 없음, `ok`와 관계 모호 | ◐ | 반영: 파일 단위 비율(읽은 대상 파일/대상 파일), `ok`와 독립. GLOSSARY에 추가 |
| S11 | C6·B8 | 중간 | `catalog_busy`가 조회·검색에도 발생, 재시도 정책 없음 | ◐ (R07 실측) | 반영: `retry_after_ms`, CLI 내부 지수 백오프 최대 3회, 종료 코드 고정 |
| S12 | B9 | 중간 | 오류 종류·종료 코드 표 불일치(`locked` 대 `source_locked`, 시간 초과 없음) | ◐ | 반영: types.py에 오류 종류·종료 코드 단일 표 |
| S13 | A5 | 중간 | 명령 전후 검사는 사후 감지라 생성 후 삭제 파일을 놓치고 큰 폴더에서 비용·오탐 | — | 반영: 검사 범위를 연 파일의 형제 패턴 + cwd `.tmp`로 좁히고 "보조 장치"로 명시, 테스트에서는 폴더 쓰기 감시(watchdog)로 생성·삭제 포착 |
| S14 | A6 | 중간 | `tempfile`·Kiwi/bm25s 저장 위치 미지정 | ◐ (tempfile 기본 `%TEMP%`) | 반영: 시작 시 `tempfile.tempdir`·TMP/TEMP = `.ldx/tmp`, bm25s 저장 = `.ldx/index/`(search 소유, 카탈로그 버전 함께 저장) |
| S15 | A7 | 중간 | `.ldx`를 이름으로 제외하면 원본 안의 동명 폴더도 빠짐, 정션 판정 API | ◐ | 반영: `samefile`로 ldx 자신의 `.ldx`만 제외 + limitation 기록, 정션은 `os.path.isjunction`/reparse point |
| S16 | B2 | 높음 | profile·search가 원본에 닿는 경로 미표시 | ◐ | 반영: profile·search는 engine의 등록된 뷰만 읽음 |
| S17 | C8·C9 | 중간 | 재구현 훈련 관문 측정 불가, AST 검사 우회(importlib, Path.read_*, 문자열 SQL) | ◐ | 반영: 시드로 표본 모듈 선정 → 새 서브에이전트에게 tests/·GLOSSARY만 주고 재작성 → 같은 테스트 100% 통과 기록. AST 금지 목록 확대 + 우회 픽스처 테스트 |
| S18 | B3·B4·B5·B6·B13 | 높음 | 문서가 v1 그대로: README 구조·FastAPI·`mode=ro` 규칙, subflows.yaml(authorizer·coverage·`{파일}_{시트}`·효과 플래그), dependencies.md(-wal 정정 누락·openpyxl), `.gitignore`에 `.ldx/` 없음 | ◐ | `.gitignore`는 즉시 수정. 나머지 문서는 v3 반영 때 일괄 수정 |
| S19 | B12 | 중간 | MVP 과다(검색기 4종 동시, 출력 형식 4종, 패싯), 누락(소스 설정 저장, 스냅샷 수명 관리, doctor 항목) | — | 반영: ①의 시나리오로 범위 확정 |
| S20 | C10 | 낮음 | FAT·네트워크 드라이브 mtime 해상도, 대용량 xlsx 메모리, n-gram 색인 크기, RRF 독점, 한글 뷰 이름 NFC | — | 반영: 볼륨 감지 시 강제 재해시, 크기 상한 경고, 뷰 이름은 내부 ID, NFC 테스트 |

## v1 반영 확인 (세 검증자 종합)
닫힘: R03, R11(약함), R13, R14, R16, R18. 부분: R01·R02(S01), R04·R05(S03), R07(S11), R08·R10·R15·R19·R21·R24(문서 미반영 S18), R09·R25(S04), R12(복사 공유 모드), R17(골든 테스트 관문 없음), R20(S06), R26(S08). 안 닫힘: R22(문서), R27(doctor 항목).

## 메인 판단
- 원본을 실제로 건드리는 구멍(S01)이 v2에서도 하나 남았고, v1 대책(헤더 판별)이 불완전했던 탓이다. 대책은 "부속 파일이 하나라도 있으면 스냅샷, 원본은 sqlite3 `immutable=1`로만"으로 더 보수적으로 바꾼다.
- 두 검증자가 독립적으로 "승인한 순서 위반"(S06)을 지적했다. 다음 작업은 그림 v3가 아니라 ① 사용 시나리오·수용 테스트 작성이 맞다. v3는 ①의 속성으로 다시 그린다.
