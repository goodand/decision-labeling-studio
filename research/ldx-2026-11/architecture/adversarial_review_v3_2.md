# 설계 v3.2 적대 검증 판정표 (2026-11-03)

대상: architecture_v3_2.png, runtime_v3_2.png (커밋 7dba5d9). 검증자 opus 4명(workflow wf_0f423186-e59): A 원본 불변 / B 구조·재사용 / C 실행 흐름·시나리오 / D 응집도·결합도·의존성. 메인 사전 지적(비공개): 남은 scan.lock 판정, scan.py 쓰기 표시 누락, SC7 지정 위치 — 셋 다 검증자도 독립 지적.
재현: ✔ 메인 직접 재현, ◐ 검증자 재현·코드 확인, — 추론.

## v3.1 지적 닫힘 (4명 종합)
- 닫힘: Y4, Y6(웹), Y7(search), Y8(WAL·짧은 트랜잭션), Y9, Y10(source add), Y12, Y13, Y15, Y17, Y18(export)
- 부분: Y1(→Z10·Z11), Y2(→Z12), Y3(→Z3), Y5(→Z5·Z9), Y6(query→Z7), Y7(query→Z17), Y10(.ldx 위치→Z14), Y11(→Z1·Z18), Y14(→Z15), Y16(→Z17)

## 새 지적과 결정

| ID | 출처 | 심각도 | 지적 | 재현 | 결정 |
|---|---|---|---|---|---|
| Z1 | A-N1 | 치명 | ldx가 원본 `-journal`을 일반 `open()`(shutil 포함)으로 1.4초 넘게 쥐면 다른 프로세스의 COMMIT이 `disk I/O error`로 실패하고 **사용자 쓰기가 사라짐**. Excel 저장 방해(Y11)와 같은 원인(FILE_SHARE_DELETE 없음) | ✔ 4초 쥐면 커밋 실패·a=2 0행 / ✔ `CreateFileW`(SHARE READ·WRITE·DELETE)로 열면 4초 쥐어도 커밋 성공·1000행 | 원본 접근(stat 외 복사·바이트 읽기·해시)은 전부 공유 옵션 READ·WRITE·DELETE로 여는 함수 하나(`signature`/`snapshot`이 공유)만 사용. 수용 테스트 "복사 중 다른 프로세스 COMMIT 성공" 추가 |
| Z2 | C-N1 | 치명 | scan 재시도가 같은 세대 폴더를 재사용하면 앞 시도의 `<ID>.db-journal`이 새 본체에 롤백으로 적용 → 찢어진 사본(quick_check ok) | ◐ | 시도마다 고유 폴더(세대+시도 ID)의 빈 `tmp`에서 사본을 완성한 뒤 rename. 복사 전 사본 쪽 부속 파일 없음 확인 |
| Z3 | A-N2·B-N2·C-N3·D-N2 | 높음 | gc가 scan.lock 없이 돌아 커밋 전 새 사본·재기동용 이전 사본을 지울 수 있음. "serve는 catalog 읽기 전용" 문구와 gc 모순 | — | gc는 scan.lock을 비차단으로 잡았을 때만, "등록됐다가 교체된" 세대만 삭제. 미등록 폴더는 잠금을 쥔 scan만 정리. serve는 쓰는 목록을 catalog에 임차(lease) 기록, gc는 이를 참조로 셈. 시그니처가 같아도 포인터의 사본이 없으면 "바뀜" |
| Z4 | A-N8·C-N2 | 높음 | scan.lock을 파일 존재로 판단하면 scan이 죽은 뒤 영구 busy | ◐ | 열린 핸들에 OS 잠금(`msvcrt.locking`)을 걸어 프로세스가 죽으면 자동 해제. 오류 종류 `scan_busy`(+ 잡은 pid) 분리 |
| Z5 | B-N1 | 높음 | Kiwi 형태소 사이드 표는 결과를 늘리지 않음(부분 문자열 검색이 토큰 일치를 포함). 효과는 어간이 바뀌는 동사뿐. 비용: 디스크 ×2.7→×3.7, scan 시간, kiwi 버전 결합, 열 정보 상실, R23과 불일치 | ✔ 사이드 표를 빼도 13개 질의 결과 동일, 차이는 "빌려준"·"들어간"(어간 변화)만 | **최소 구성에서 사이드 표 제거.** textindex = 질의 정규화만(형태소 → 원문 trigram/LIKE). 사이드 표는 확장 자리(동사 질의 실패가 실제로 나올 때). 색인 시점 Kiwi 없음 → kiwi 버전 변경이 rescan을 요구하지 않음, 디스크 기준 ×3 |
| Z6 | C-N8·B-N7·D-N3 | 높음 | 파생 표(FTS shadow)가 사본에 섞여 `sqlite_master` 표 수가 원본과 다름(SC6 "테이블이 몇 개" 오답), 원본에 `t_fts`가 이미 있으면 `enable_fts` 실패 | ◐ | 색인은 별도 파일 `<ID>__idx.db`. 사본 스키마 = 원본 스키마. search 내부 연결만 색인을 붙임(사용자 query는 여전히 ATTACH 거부). `show`는 catalog 표 목록 |
| Z7 | C-N5·N6·D-N5 | 높음 | SC7 지정 입력이 없음. query의 "원문 제거"를 결과 열 후처리로 하면 `select 메모 as m`·`hex()`·`substr()`로 샘. authorizer IGNORE는 `count … where like`를 조용히 0으로 바꿈 | ◐ | `source add --positions-only <시트 패턴>`으로 받아 catalog에 기록. query는 SC7 표의 텍스트 열 READ를 **DENY**(`sql_rejected`), `_source_row`·`count(*)`만 가능. export도 같은 가드 |
| Z8 | C-N4 | 높음 | 변환 규칙·SC7 지정·ldx 버전이 바뀌어도 원본 시그니처가 같아 재변환 안 됨 → "scan 필요" 무한 반복 | — | 시그니처에 변환 설정 해시(ldx 버전·머리행 규칙·SC7 지정) 포함, `scan --rebuild [source]` 추가 |
| Z9 | C-N7 | 높음 | 한 단어 안 형태소 결합이 OR라 "디자인시제품"이 "디자인"만 있는 행까지 잡음, 순위 없음 → 잘림이 행 번호 순, compare가 잘린 결과에서 정확 일치를 놓침(602행 중 601건, 정확 일치 행이 100행 밖) | ◐ | 단어 안 형태소는 AND, 원단어 trigram은 OR 대안. 정렬: 정확 일치 > 구문 일치 > 형태소 전부. compare는 소스마다 `=` 질의를 잘림 전에 먼저. 잘림은 소스별, `total_rows`는 소스별·합계 |
| Z10 | A-N4 | 중간 | 1GB 넘는 롤백 모드 DB는 다른 프로세스가 쓰기 트랜잭션 중이면 1GB 지점 잠금 바이트 때문에 복사가 항상 실패(budget_all 2.2GB 해당), 재시도 상한 없음 | ◐ | 청크 복사에서 잠금 바이트 페이지(0x40000000~, SQLite 미사용)는 0으로 채움. 재시도 3회, 넘으면 `source_locked` + 이전 사본 유지 |
| Z11 | A-N5 | 중간 | 복사한 핫 저널에 super-journal 경로가 있으면 사본 복구 시 SQLite가 **원본 폴더의 파일을 열고 지움**(A02 위반), 없으면 롤백 생략 → 찢어진 사본 | ◐ | 사본을 열기 전에 복사한 저널 끝의 super-journal 기록을 0으로 지움 → 항상 마지막 커밋 상태로 롤백 |
| Z12 | A-N6 | 중간 | `DirEntry.stat()` 캐시는 같은 크기 덮어쓰기를 늦게 반영 → WAL 변경 놓침 | ◐ | 시그니처·전후 비교는 파일마다 `os.stat`, DirEntry 값 금지 |
| Z13 | A-N7 | 중간 | xlsx·csv에 전후 stat 비교 없음, catalog에 어느 시점 stat을 기록하는지 미정(읽은 뒤면 P1 위반) | — | 모든 형식에 "읽기 전 stat == 읽은 뒤 stat일 때만 채택", catalog에는 읽기 전 stat 기록 |
| Z14 | A-N3 | 중간 | `.ldx` 루트 위치 미정(cwd 기준이면 원본 폴더에서 실행하는 순간 `.ldx/` 생성), overlap 검사가 source add에만, `startswith` 판정은 `src2`를 `src` 안으로 오판 | ◐(commonpath) | `.ldx` 루트 고정(`LDX_HOME`, 기본 사용자 홈). 모든 명령 시작과 `.ldx` 생성 전에 overlap 검사(`os.path.commonpath`), 인자는 chdir 전에 realpath |
| Z15 | D-N1·B-N3 | 중간 | 시그니처 규칙이 scan에 있어 catalog.staleness가 순환 의존하거나 중복 구현. staleness가 해시까지 보면 배너·질의마다 원본을 엶 | — | `signature.py` 분리(scan·catalog가 의존). `staleness()`는 stat만(원본 열지 않음), 해시는 scan 안에서만 |
| Z16 | D-N4 | 중간 | 범례 "모든 DB 연결 immutable"을 catalog에 적용하면 serve 폴링이 변화를 못 봄 | ◐ | 사본만 `mode=ro&immutable=1`, catalog는 `mode=ro`(WAL) |
| Z17 | B-N4·N5·N6·N8, D-N6·N7·N8 | 중간 | `source add`·`serve`가 app 밖, cli→serve 간선 없음(기본 설치에서 datasette import 실패 위험), 배너와 감독이 serve.py 한 파일, 사본 열기 코드 중복(query는 재시도 없음), export가 search·query를 다시 실행, 중단 상자와 오류 종류 불일치, searcher hook에 짝 indexer 없음 | — | app에 `source_add`, cli→serve 지연 import, `banner.py` 분리, `catalog.open_current(source)`가 URI·재시도·세대 시각 담당, app이 결과 행을 export에 전달, 오류 종류 `export_rejected`·`scan_busy` 추가, hook 짝 `indexer(table)`/`searcher(...) -> (hits, limitations)` |
| Z18 | 여러 명 | 낮음~중간 | 오래 남은 `~$`·LibreOffice `.~lock.*#`, 확장자 대소문자·미지원 확장자 누락, `read_status` 값 정의·원본 삭제 처리, SC1 GUI "저장하면 바로 반영" 미충족, 짧은 단어 LIKE 전수 탐색 비용, export를 `.ldx/exports/`로 한정(A17보다 좁음), pyproject 미반영(openpyxl은 테스트용 dev 유지) | — | `~$`는 단서로만(나이·본체 안정성으로 남은 잠금 판정), normcase 비교·미지원 확장자 개수 limitation, `read_status` = fresh/stale_kept/excluded/failed·원본 삭제 시 포인터 내림, **serve가 60초마다 stat만으로 staleness 확인 → 바뀌었으면 scan 실행(SC1 GUI 최소 구성)**, LIKE 비용은 기록 후 판단, export 한정은 사유(경로 판정 단순화) 기록, pyproject는 구현 시작 때 |

## 메인 판단
- 이번 회차의 치명 2건은 원본 바이트가 아니라 **원본을 쓰는 다른 사람의 작업**(Z1)과 **ldx 자신의 재시도**(Z2)에서 나왔다. Z1은 대책까지 메인이 재현해 확인했다.
- 최소 구성 원칙대로 Kiwi 사이드 표를 뺐다(Z5). 실측으로 효과가 없음을 확인한 기능을 빼는 첫 사례다.
- 회차별 높음 이상: v3 12건 → v3.1 18건(치명 2) → v3.2 18건(치명 2). 지적이 줄지 않는 대신 **추상 구조 → 파일 핸들·트랜잭션·재시도** 수준으로 내려가고 있다. 이 수준은 그림보다 실행 가능한 테스트로 잡는 편이 정확하다.
