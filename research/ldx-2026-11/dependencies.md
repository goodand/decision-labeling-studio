# 의존성 분석 (2026-11-02)

고정: `pyproject.toml` + `uv.lock` (직접 7개, 전이 포함 19개). 설치는 `uv sync --system-certs`
(이 PC는 uv에 시스템 인증서가 필요). Python 3.12.

## 직접 의존성과 실측 결과

| 패키지 | 버전 | 라이선스 | 쓰는 Subflow | 이 PC 실측 (scratchpad probe.py) |
|---|---|---|---|---|
| duckdb | 2.0.0 | MIT | 2 Parser, 3 Profiler, 5 Query | `INSTALL sqlite` 성공(extensions.duckdb.org 열림). `read_xlsx(sheet='예산표')` 성공. CP949 CSV는 `encoding='cp949'` 지정 시만 성공(기본 UTF-8은 오류). SQLite `ATTACH (TYPE sqlite, READ_ONLY)`에서 DELETE·CREATE 차단, 파일 해시 불변, -wal/-shm 미생성(3.5MB 사본) |
| python-calamine | 0.9.0 | MIT | 2 Parser(Excel) | 한글 시트명 `예산표` 읽기 성공 |
| openpyxl | 3.1.5 | MIT | 2 Parser(Excel, 대안) | 한글 시트 쓰기·읽기 성공(시험 파일 생성용) |
| rapidfuzz | 3.14.6 | MIT | 7 Fuzzy | 설치만 확인 |
| kiwipiepy | 0.24.1 | Apache-2.0 | 6 Full-text | "중소기업 창업 지원 사업" → 중소기업/창업/지원/사업 |
| bm25s | 0.3.16 | MIT | 6 Full-text | 설치만 확인 |
| typer | 0.27.3 | MIT | 18 Agent CLI | 설치만 확인 |

## 전이 의존성

| 패키지 | 버전 | 라이선스 | 끌어온 쪽 |
|---|---|---|---|
| numpy | 2.5.4 | BSD-3-Clause 외 관대 | bm25s, kiwipiepy |
| kiwipiepy_model | 0.24.0 | Apache-2.0 | kiwipiepy |
| tqdm | 4.70.1 | MPL-2.0 AND MIT | kiwipiepy |
| colorama | 0.4.6 | BSD | tqdm, typer |
| et_xmlfile | 2.0.0 | MIT | openpyxl |
| rich 15.0.0, markdown-it-py 4.2.0, mdurl 0.1.2, pygments 2.21.0 | — | MIT / BSD-2 | typer |
| shellingham 1.5.4 | — | ISC | typer |
| annotated-doc 0.0.5 | — | MIT | typer |

판단: 전부 관대한 라이선스. tqdm의 MPL-2.0은 파일 단위 약한 카피레프트라 수정 없이 의존성으로 쓰는 한 의무 없음.

## 일부러 넣지 않은 것
- FastAPI 등 화면 기술: 미정(Subflow 17 결정 후)
- Docling: 제외. 문서 파싱은 이 PC의 govparse MCP 사용
- Lean: 이 PC 네트워크에서 설치 불가(GitHub 릴리스 파일 서버 차단)

## 남은 확인
- 2GB SQLite·WAL 모드 DB에서 READ_ONLY ATTACH 동작과 부속 파일 생성 여부 (W3 실측 항목)
- duckdb 2.0의 sqlite 확장 버전 고정 방법(확장은 uv.lock 밖이라 별도 기록 필요)
- Kiwi + bm25s 결합 검색 품질
