# 설계 v3.1 적대 검증 판정표 (2026-11-03)

대상: architecture_v3_1.png, runtime_v3_1.png (커밋 e8d3e03). 검증자 opus 4명(workflow wf_a1407dff-c72): A 원본 불변 / B 구조·재사용 / C 실행 흐름·시나리오 / D 응집도·결합도·의존성. 메인 사전 지적(비공개): 디스크 점검 순서, scan 완료 신호, 64KB 해시가 원본을 매번 엶 — 모두 검증자도 독립 지적.
재현: ✔ 메인 직접 재현, ◐ 검증자 재현·코드 확인, — 추론.

## v3 지적 닫힘 (4명 종합)
- 닫힘: X2(단, Y5), X4, X9, X11, X12, C4, C9, A8·A9, A10, B7, `#` 경로
- 부분: X1(→Y3), X3(→Y5), X5(→Y4·Y13), X6(→Y6), X7(pyproject 미반영, 구현 시작 때), X8(→Y1·Y11), X10(→Y9), A6(→Y2), A7(→Y14), A11(→Y11), B5(→Y15), C7·C8(머리행·빈 시트 그림 누락), C10(→Y18)

## 새 지적과 결정

| ID | 출처 | 심각도 | 지적 | 재현 | 결정 |
|---|---|---|---|---|---|
| Y1 | A-N1 | 치명 | 쓰기 중인 DB를 본체만 복사하거나 부속 파일을 원래 이름(`x.sqlite-wal`)으로 복사하면 사본 `<ID>.db`가 부속 파일을 못 찾아 찢어진 데이터·WAL 누락이 오류 없이 채택(2만 행 중 1,955행 소실, integrity 실패, 전후 stat은 같음) | ◐ | 부속 파일은 `<ID>.db-wal`·`<ID>.db-journal`로 이름을 바꿔 복사 → 사본을 읽기·쓰기로 열어 롤백·체크포인트 → `quick_check` 실패면 채택 안 하고 limitation. 전후 stat은 본체+부속 파일 묶음 |
| Y2 | A-N2 | 높음 | WAL 원본은 커밋해도 본체 (size, mtime, 앞뒤 해시) 불변 → 바뀐 파일을 놓침 | ◐ | 변경 시그니처 = 본체 + `-wal`·`-journal`의 존재·크기·mtime |
| Y3 | D-N1·C-N3·A-N8·B-N9·메인 | 치명 | 세대 구조 모순: scan은 바뀐 파일만 새 세대, serve는 한 세대 폴더만 열고 통째로 삭제 → 현재 사본까지 삭제·반쪽 삭제(WinError 32). CLI만 쓰면 세대가 쌓임. 완료 신호 미정 | ◐ | **파일 단위 세대**: catalog가 소스별 현재 세대 경로를 가리킴. serve는 glob 대신 catalog 경로 목록 사용. `catalog.gc_generations()` = 참조 0이고 지울 수 있는 세대만 삭제, 실패는 기록 후 다음에 재시도, scan 끝·serve 재시작 뒤 둘 다 호출. 신호 = serve가 catalog 세대 번호를 폴링. serve에 ✎ 표시. 재기동 실패 시 이전 목록으로 재기동 |
| Y4 | B-N1·C | 높음 | authorizer 허용 목록(SELECT·READ·FUNCTION)이 FTS5 MATCH를 막음(내부 `PRAGMA data_version`), `WITH RECURSIVE`도 거부 | ✔ | 허용 목록에 읽기 전용 PRAGMA(`data_version`, `table_info`, `table_xinfo`, `index_list`)와 `SQLITE_RECURSIVE` 추가, 나머지 PRAGMA 거부. 쿼리 가드 실험에 FTS·재귀·pragma 함수 사례 추가 |
| Y5 | B-N3·N4·N5·N6, C-N1 | 높음 | (1) 질의 전체 길이로 분기 → 여러 단어 안의 2글자 단어 무시, 엉뚱한 행 섞임 (2) 문구 통째 MATCH → 어순·떨어진 단어 0건, sqlite-utils `search()`보다 나쁨 (3) Kiwi 2음절 형태소("패션을"→"패션")는 trigram 0건 (4) Kiwi 열이 사용자 표에 노출(A16 위반)·사본 스키마 변형·WITHOUT ROWID 실패 | ◐ | **단어별 처리**: 질의 → Kiwi 형태소 → 각 형태소 3글자 이상은 MATCH(sqlite-utils `quote_fts` 재사용), 미만은 LIKE, AND로 결합. Kiwi 형태소는 **별도 사이드 표 + unicode61 FTS5**(rowid 연결, Datasette에서 숨김), 사용자 표는 손대지 않음. WITHOUT ROWID 표는 "FTS 없음→limitation". 수용 테스트에 2음절 명사+조사, 어순, 떨어진 단어 추가 |
| Y6 | B-N2·C | 높음 | SC7 표를 hidden·allow:false로 막아도 같은 DB면 임의 SQL로 원문이 읽힘 | ◐ | SC7 대상 시트는 **별도 DB 파일**로 변환해 serve 목록에서 제외. CLI query·export에도 SC7 표는 positions-only 강제 |
| Y7 | A-N7·C-N4 | 높음 | `immutable=1`만 주면 사라진 사본 경로에서 빈 DB를 새로 만들고 0건 반환 | ✔ | 사본은 항상 `mode=ro&immutable=1`. 열기 실패면 catalog 세대를 다시 읽어 1회 재시도 후 limitation |
| Y8 | D-N2·C-N5 | 높음 | catalog 잠금 범위 미정. rollback 모드에서 scan 내내 쓰기 트랜잭션이면 읽기가 수 분 `catalog_busy`, 읽기가 열려 있으면 scan COMMIT 실패 | ◐ | catalog.db는 WAL(.ldx 안이라 `-shm` 허용). scan끼리는 별도 잠금 파일. 새 세대 기록은 마지막 짧은 트랜잭션 하나 |
| Y9 | C-N2·메인 | 높음 | 디스크 점검이 순회 전, ×2.3은 SQLite 원문 FTS만의 값. 합성 xlsx는 표 ×4.9, 원문 FTS ×12.5, Kiwi 포함 ×19.7 | ◐ | 변경 판별 뒤 점검. 형식별 배율(SQLite·엑셀·CSV) + Kiwi 표 + 아직 못 지운 세대 합산. 실제 사본으로 엑셀 배율 실측 |
| Y10 | A-N3 | 높음 | `.ldx`가 원본 폴더 안에 있으면 모든 쓰기가 원본 폴더에 새 항목(A02 위반) | — | `source add`에서 원본 루트와 `.ldx` 루트를 realpath·normcase로 비교, 포함 관계면 거부("`.ldx` 자신 제외" 규칙 대체) |
| Y11 | A-N4 | 높음 | ldx가 원본 핸들을 연 동안 Excel의 임시파일→원래 이름 교체가 막힘(WinError 32·5), 확장자 없는 Excel 임시 파일은 제외 목록에 없음 | ◐ | 순회는 확장자 허용 목록(xlsx·xls·csv·sqlite·db)만. 같은 폴더에 `~$<이름>`이 있으면 열지 않고 limitation "열려 있음", 다음 scan으로. 앞뒤 해시는 (size, mtime) 변화가 없을 때만 계산 |
| Y12 | D-N4·N5 | 높음 | CLI search마다 Kiwi 모델 로드 약 1.8초. 색인·질의의 Kiwi 설정이 어긋나면 조용히 누락 | ◐ | 질의에 한글이 있을 때만 Kiwi 로드, 소요 시간 기록. `textindex.py` 하나가 색인용 형태소와 질의 정규화를 모두 소유, 세대 메타에 kiwi 버전·옵션 기록, 불일치면 limitation "scan 필요". 상주 정규화는 확장 자리 |
| Y13 | B-N8·C-N10 | 중간 | CLI query 실행 시간 상한 없음(웹은 1초) | ◐ | 표준 `set_progress_handler`로 중단, 오류 종류 `query_timeout` 추가 |
| Y14 | D-N8·A-N5·A-N6 | 중간 | "원본 바뀜" 판정이 scan·search·배너에서 기준이 다름, query엔 없음, 배너는 catalog 시각을 표시해 서버 실제 세대와 어긋날 수 있음 | — | `catalog.staleness(path)` 하나로 통일, search·query·배너 모두 사용, query 봉투에도 `snapshot_at`. 배너는 Datasette가 실제 연 파일의 세대 시각 표시 |
| Y15 | B-N7·C | 중간 | canned query는 DB 하나 단위, 여러 소스는 crossdb(최대 10개) + SQL 생성 → 두 번째 compare 구현 | ◐ | 최소 구성에서 웹 대조 제외. compare는 CLI JSON만, 웹 대조는 확장 자리 |
| Y16 | D-N6·N9 | 중간 | commands.py가 typer 진입점이자 배너 API(변경 이유 2개), 배너가 typer·kiwi까지 끌어옴. types.py가 ②층이라 ③층이 위로 의존 | — | `cli.py`(typer 인자 처리) / `app.py`(봉투 반환 함수) 분리, 배너는 catalog 읽기 전용 조회. types.py는 맨 아래 공통층. 모듈 의존 그래프를 그림에 텍스트로 |
| Y17 | D-N3·N7 | 중간 | kiwipiepy는 LGPL이 아니라 Apache-2.0(메인 v3 판정 오류). datasette-search-all이 [web] 밖이라 기본 설치에 datasette가 딸려 옴 | ✔(라이선스) | 범례를 Apache-2.0으로 수정. `[web] = datasette==0.65.5, datasette-search-all==1.1.4` |
| Y18 | 여러 명 | 낮음 | export는 `os.rename`만(`os.replace` 금지), 부속 파일은 본체에 묶어 세기, `read_ratio` 분모 두 개 → `read_ratio` + `read_scope{files, tables}`, 첫 행=머리행·빈 시트 0행 그림 표기, scenarios.md 이름 갱신(positions_only 등), 검색기 hook `searcher(query, tables) -> hits` 명명, query 대상 DB 지정 인자(`--source`) | — | 모두 반영 |

## 메인 판단
- v3 치명·높음 12건 중 7건은 닫혔고 나머지는 세부가 남았다. 새 치명 2건(Y1 찢어진 사본, Y3 세대 모순)은 v3.1에서 바꾼 부분이 아니라 **v3부터 있던 복사·세대 설계의 빈칸**이 실험과 함께 드러난 것이다.
- 재사용 쪽 교훈: 직접 짠 검색 접착 코드(문구 MATCH)가 재사용 코드(sqlite-utils `search()`)보다 나빴다(Y5). 원칙대로 재사용을 먼저 쓴다.
- 다음: v3.2 그림(Y1~Y18 반영) → 적대 검증. 실험 추가: Y1 사본 복구·quick_check, Y4 확장 가드, Y5 단어별 검색, Y9 실제 엑셀 배율.

## 대책 실측 F1~F4 (2026-11-03, scripts/evidence/exp_v31.py·exp_f4.py)

| 실험 | 결과 | 결정 갱신 |
|---|---|---|
| F1a 핫 저널 | 다른 프로세스가 2만 행 갱신 도중 멈춤. 본체만 복사: 커밋 안 된 a=2가 19,893행 섞임, **quick_check는 ok**. 부속 파일을 `<ID>.db-journal`로 복사 후 열기: 롤백되어 a=2 0행, 2만 행 정상 | Y1 채택. **quick_check로는 찢어진 사본을 못 잡음** → 부속 파일 이름 맞춤 복사가 핵심, quick_check는 손상 감지용 보조 |
| F1b WAL | 체크포인트 안 된 500행: `<ID>.db-wal`로 복사하면 500행, 원래 이름으로 복사하면 표 없음 | Y1 채택 |
| F2 확장 가드 | 허용: FTS MATCH, WITH RECURSIVE, `pragma_table_info()`, 일반 SELECT. 거부: pragma 쓰기·DELETE·ATTACH·여러 문장·load_extension. 3중 카티전 곱은 1초 뒤 `interrupted`. `pragma data_version=1`은 허용되나 읽기 전용 값이라 무해 | Y4·Y13 채택. 허용 PRAGMA는 이름 목록(data_version·table_info·table_xinfo·index_list)으로, 인자 허용 |
| F3 단어별 검색 | 13개 질의 모두 기대대로: 패션·패션을·기업을·융자를·창업을·시제품 디자인(어순)·패션 시제품(떨어진 단어)·디자인시제품·12 지원·P-2026·안전장치를·제작하는·패션 디자인 시제품(엉뚱한 행 섞임 없음). 사용자 표 열은 `_source_row, 내용`만(사이드 표로 노출 없음) | Y5 채택 + 보완: Kiwi가 같은 단어를 맥락 따라 다르게 쪼갬("안전장치를"→안전장치 / 문서 안→안전+장치) → **각 형태소를 사이드 표와 원문 trigram(3글자 이상)·LIKE(미만) 양쪽에서 찾음** |
| F4 실제 엑셀 | 공고 마스터 5.91MB(원본 폴더 불변, 변환 DB는 측정 후 삭제, 내용 미출력): 시트 표 2개, 표만 ×1.0, 원문 FTS ×2.7, Kiwi 사이드 표 포함 ×3.7 | Y9: 엑셀 배율 ×3.7(합성 ×19.7은 과대). SQLite ×2.24(E5) + Kiwi분 → 디스크 기준 ×4로 시작, 실측 누적 시 갱신 |
| F4 Kiwi 속도 | 셀마다 호출 9~23만 자/초, **묶음 호출(기본 스레드, CPU 32) 357만 자/초**(약 15배) | convert는 Kiwi를 묶음으로 호출(`tokenize(iterable)`). 고유값 기준 budget_all 약 3억 자 → 약 90초(추정) |
