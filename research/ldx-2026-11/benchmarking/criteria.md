# 벤치마킹 공통 기준 (v1, 2026-11-02)

모든 후보를 같은 기준으로 채운다. 기준마다 0~5점을 주고 가중치를 곱해 100점 만점으로 환산한다.
점수마다 근거(file:line, 문서 URL, 실측 로그)를 붙인다. 근거가 없으면 점수 대신 "확인 못함"으로 둔다.

| ID | 기준 | 가중치 | 5점 | 0점 |
|---|---|---|---|---|
| C1 | 원본 불변 보장 | 25 | 원본 쓰기 경로가 구조적으로 없음(읽기 전용 열기 + 쓰기 문장 차단 + 우회 불가) | 기본이 쓰기 모드이거나 원시 SQL로 원본 수정 가능 |
| C2 | 로컬 파일 지원과 폴더 연결 | 15 | CSV·Excel(다중 시트)·SQLite를 폴더째 연결, 파일 간 JOIN | 한 형식만, 파일 하나씩 |
| C3 | 한글 처리 | 10 | 한글 경로·시트·열 이름 보존, CP949 CSV 읽기 | 비ASCII 이름 변형 또는 인코딩 깨짐 |
| C4 | 대용량(2GB SQLite) | 10 | 지연 로딩·페이징으로 전체 적재 없음 | 테이블 전체를 메모리에 적재 |
| C5 | 에이전트 제어 | 15 | CLI/MCP/API가 GUI와 같은 기능, JSON 출력·오류 규약 | GUI 전용 |
| C6 | 비SQL 탐색 UX | 10 | 전체 검색·필터·열 프로파일을 SQL 없이 | SQL 작성만 가능 |
| C7 | 재사용성(구조·라이선스) | 10 | 엔진·인터페이스 분리, 관대한 라이선스, 부분 재사용 쉬움 | 단일 덩어리 또는 재사용 제한 라이선스 |
| C8 | 이 PC 설치 용이성 | 5 | PyPI/npm/git clone만으로 설치(GitHub 릴리스 파일 서버 차단 환경) | 막힌 경로나 계정·클라우드 필수 |

## 이 PC의 제약 (C8 판단용)
- 막힘: release-assets.githubusercontent.com, objects.githubusercontent.com, raw.githubusercontent.com, download.visualstudio.microsoft.com
- 열림: github.com(git clone), PyPI(uv는 --system-certs), npm registry, extensions.duckdb.org, open-vsx.org, conda.anaconda.org

## 후보
- 1차(완료, 기준표 재채점 필요): DuckLocal, Octa, REA, Duck-UI, Dataloupe, DBML ERD Viewer
- 2차(이번): Datasette, Harlequin, Evidence, Rill, DuckDB UI, Power BI Desktop, KNIME
