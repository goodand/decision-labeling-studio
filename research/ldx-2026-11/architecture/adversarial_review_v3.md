# 설계 v3 적대 검증 판정표 (2026-11-03)

대상: architecture_v3.png, runtime_v3.png (커밋 57aa09d). 검증자 opus 4명: A 원본 불변 / B 구조·재사용 / C 실행 흐름·시나리오 / D 응집도·결합도·의존성. M = 메인이 이미지 먼저 읽고 낸 지적(검증자에게 비공개).
재현: ✔ 메인 직접 재현, ◐ 검증자 재현 또는 코드 확인, — 추론만. 실험 열의 E번호는 아래 "다음 실험"에서 대책을 실측한다.

## 치명·높음

| ID | 출처 | 지적 | 재현 | 결정 | 실험 |
|---|---|---|---|---|---|
| X1 | A1·B3·C5·D3·D6·M3 | Datasette가 `-i`로 연 사본을 scan이 교체 못 함(WinError 5), 열린 연결은 옛 데이터를 계속 보여 줌. 새 DB는 서버 재시작 전 안 보임 | ✔ | 사본은 세대별 새 파일명 `<ID>.<세대>.db`, catalog에 현재 세대 기록. 서버는 `ldx serve`로 감싸고 scan 후 세대 교체(런타임 add/remove 또는 재시작). 옛 세대는 핸들 닫힌 뒤 삭제 | E1 |
| X2 | C1·B4 | trigram은 2글자 질의("패션", "디자", "12") 0건 | ✔ | 질의 길이 < 3이면 LIKE/instr로 찾고 limitation에 "짧은 질의, 색인 미사용" | E3 |
| X3 | C2·M | kiwi가 "0건일 때만" + 질의만 정규화 → 효과 없음, 미설치 | ◐ | 색인 시점에 Kiwi 형태소(명사·어근) 열을 따로 만들어 FTS에 함께 넣고, 질의도 같은 방식으로 정규화. 미설치면 limitation | E3 |
| X4 | C3·M2 | CSV 경로 없음, calamine은 CSV 불가 | ◐ | scan에 CSV 분기: UTF-8(BOM 포함) → CP949 순 시도, 판정 인코딩을 catalog에. 재사용: sqlite-utils `rows_from_file` / 표준 csv | E4 |
| X5 | B1·D2 | `validate_sql_select`는 첫 단어만 봄(다중 문장·load_extension·주석 통과) | ◐ | CLI query는 Datasette 내부를 import하지 않음. sqlite3 `set_authorizer`(SELECT·READ·FUNCTION만 허용) + `enable_load_extension(False)` + 한 문장 실행 + `query_only` | E2 |
| X6 | B2·C12·M4 | Datasette 웹 화면은 commands.py를 거치지 않아 봉투·limitation·positions_only가 적용 안 됨 | ◐ | "단일 진실"의 범위를 ldx 명령으로 좁혀 그림에 명시. 웹은 배너 플러그인으로 limitation 표시, SC7 대상 표는 Datasette에 올리지 않음 | — |
| X7 | D1·D7·D8 | pyproject에 datasette·sqlite-utils 없음, duckdb·bm25s·rapidfuzz는 미사용, openpyxl은 dev에만 | ◐ | 구현 시작 때 의존성 정리: datasette 0.65.5·sqlite-utils 고정 추가(`[web]` optional로 datasette), duckdb·bm25s·rapidfuzz 제거, export는 sqlite-utils·csv만(openpyxl 제외) | — |
| X8 | A2·A3·A4 | 원본 읽는 동안 Excel 저장 방해 가능, 엑셀은 전후 stat 비교 없음, 부속 파일 시점 어긋남 | ◐(A2) | 원본은 한 번에 읽고 즉시 닫음. 엑셀·CSV도 전후 (size, mtime_ns) 비교 후 다르면 재시도→limitation. 복사 시점에 `-wal`·`-journal` 있으면 limitation "작업 중 사본" | E1 |
| X9 | A5 | 확장 자리 "immutable=1 직접"이 "원본 직접 열지 않음"과 충돌 | — | 확장 자리에서 삭제 | — |
| X10 | C6·M1 | 2.2GB 사본+FTS 디스크·시간 미측정, SQLite 사본에 FTS 만드는 단계 없음 | — | scan에 "사본 FTS 생성" 단계 명시. 크기·시간은 실측 후 디스크 사전 점검 기준 | E5 |
| X11 | C11 | A14 `total_rows_exact`를 확장 자리로 미룸(수용 속성 약화) | — | 봉투 필수 필드로 복귀 | — |
| X12 | D4·D5 | scan의 변경 이유 5개, catalog 모듈·파일명 규약 암묵 공유 | — | `snapshot`·`convert` 분리, `catalog.py`가 경로·스키마 단독 담당. compare는 search 안 함수(D11, 과분리 방지) | — |

## 중간·낮음 (결정만)

| ID | 지적 | 결정 |
|---|---|---|
| A6 | (size, mtime_ns)만으로는 mtime 보존 교체 놓침 | 앞뒤 64KB 해시를 함께 비교 |
| A7 | 사본 시각·원본 변경 여부 표시 없음 | 봉투에 `snapshot_at`, 조회 때 원본 stat만 재확인해 "scan 필요" limitation |
| A8·A9 | export 경로 우회·반쪽 파일 | realpath+normcase로 원본 루트 비교, 처음엔 `.ldx/exports/`만 허용, tmp에 쓰고 `x` 모드·rename |
| A10 | cwd 모호 | 시작 시 cwd=`.ldx/tmp`, 모든 경로 절대경로 |
| A11 | Excel 잠금 파일 `~$*` | scan 제외, "열려 있음" 신호로 사용 |
| C4 | enable_fts 트리거 없음 → 재스캔 시 FTS 낡음 | 세대별 새 DB라 매번 새로 생성(X1과 함께 해소) |
| C7·C8 | 중복 열 이름 덮어씀, 병합·빈 시트 | 중복은 `_2` 접미사+원래 이름 catalog 기록, 첫 행=머리행 가정 명시, 빈 시트는 0행+limitation |
| C9·B10·D11 | compare가 부분 일치에 섞임, search 한계 상속 | 정확 일치 먼저·부분 일치 구분 표시, search limitation을 그대로 전달, 소스별 잘림 기록 |
| C10 | read_ratio가 파일 비율뿐 | 분모를 명시(파일·표 둘 다 보고) |
| B5 | 대조 전용 화면은 접착보다 큼 | 최소 구성은 CLI JSON + Datasette canned query, 전용 화면은 확장 자리 |
| B6 | Datasette 0.65 내부 결합 | 버전 고정, 공개 hook(register_routes)만 사용 |
| B7 | backup API 재사용 제안 | 원본 연결 자체 금지 규칙 유지(원본 폴더 `-shm` 생성 위험), 파일 복사 유지 — 사유 기록 |
| B8·B9·B11 | 쓰기/읽기 기능 구분, 그림 간 라이브러리 불일치, 확장 hook 이름 | v3.1 그림에서 쓰기 기능(scan·export) 색 구분, 라이브러리 목록 통일, `reader(path) -> sheets` 같은 hook 이름 표기 |
| D9·D10·D12 | click 버전 맞물림, kiwipiepy 크기(라이선스는 Apache-2.0, v3.1 판정 Y17에서 정정), 런타임 무게 | lock 생성 후 기록, kiwi는 지연 import·라이선스 기록, 웹은 `[web]` optional |

## 이름 변경 (docs/glossary/names_results.md, 로컬 Qwen + gpt-6-luna 일치)
read_completeness→`read_ratio`, `.ldx/data`→`.ldx/copies`, status→`read_status`, `_행`→`_source_row`, location_only→`positions_only`. `compare`는 유지하고 도움말 첫 줄 "나란히 보여 줌, 합치지 않음"(사용자 결정 2026-11-03).

## 다음 실험 (대책 실측, 합성 파일·사본만)
- E1 세대별 사본 + 실행 중 Datasette에서 세대 교체, 옛 세대 삭제 가능 시점
- E2 sqlite3 authorizer 쿼리 가드 공격 목록
- E3 trigram + 2글자 LIKE + Kiwi 색인 열: "패션", "디자인시제품", "시제품을", "P-2026", "12"
- E4 CSV UTF-8/BOM/CP949 판별
- E5 실제 DB 사본(budget_sme 158MB)에 FTS 생성 시 크기·시간

## 실험 결과 (2026-11-03, scripts/evidence/exp_v3.py·exp_e5.py)

| 실험 | 결과 | 결정 갱신 |
|---|---|---|
| E1 실행 중 교체 | `remove_database`→`add_database`(같은 이름, 새 세대 파일) 후에도 **옛 세대 100행을 계속 반환**(스레드별 연결 캐시), 옛 파일 삭제 WinError 32 | 실행 중 교체 금지 |
| E1 재시작 | 별도 프로세스 Datasette 종료→새 세대로 기동 1.2초, 새 세대 250행 정상, 재시작 후 옛 세대 삭제 성공. 실행 중에는 옛 세대 삭제 불가 | `ldx serve`가 scan 완료 후 서버 재시작, 옛 세대는 재시작 뒤 삭제. DB 이름이 세대마다 바뀌지 않게 `.ldx/copies/<세대>/<ID>.db`(폴더로 세대 구분, 파일명 고정). 파일명에 `.` 금지(Datasette URL 인코딩) |
| E2 authorizer 가드 | 허용: SELECT·WHERE·CTE. 거부: DELETE·INSERT·CREATE·ATTACH·pragma 쓰기·load_extension(not authorized), 다중 문장·주석 뒤 문장(한 문장 규칙), CTE DELETE(문법 오류), readfile(함수 없음). 원본 행 수 불변 | X5 결정대로 채택, Datasette 내부 함수 불필요 |
| E3 검색 | 2글자 "패션"·"디자"·"12" LIKE로 찾음. "시제품을"·"안전장치를"(조사)·"디자인시제품"(붙여쓰기)·"제작하는"(활용) Kiwi 열로 찾음. "P-2026" trigram으로 찾음 | X2·X3 결정대로 채택. Kiwi 열에 "하" 같은 잡음 형태소 → 1글자 형태소 제외 검토 |
| E4 CSV | UTF-8·UTF-8 BOM·CP949 판별 성공, 깨진 바이트는 판별 실패→limitation | X4 결정대로 채택 |
| E5 FTS 크기 | budget_sme 사본 158MB, 복사 0.1초(원본 부속 파일 없음, 원본 폴더 불변). 텍스트 열 FTS5 trigram 31개 표 생성 15초(섹션원문 6초) → 355MB(×2.24) | 같은 비율이면 budget2026.all 672MB→약 1.5GB·약 1분, budget_all 2.2GB→약 5GB·약 3.5분(추정). 디스크 여유 281GB. Kiwi 열 시간은 미측정(고유값 기준 처리 속도 125만 자/초 추정) |
