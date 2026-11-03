# 2차 벤치마킹: Power BI Desktop, KNIME (공식 문서 기준, 설치 안 함)

기준: [criteria.md](criteria.md) v1. 조사: sonnet 서브에이전트. 메인 직접 확인: ✔ 표시.

| 기준 (가중치) | Power BI | 근거 요약 | KNIME | 근거 요약 |
|---|---|---|---|---|
| C1 원본 불변 (25) | 3 | Excel·CSV·Folder 커넥터는 Import 전용. Python 스크립트 소스는 임의 실행 가능 | 2 | 리더는 읽기 전용이나 Excel Writer(기존 파일에 시트 추가), DB Writer/SQL Executor가 일급 기능 |
| C2 로컬 파일·폴더 (15) | 4 | Folder 커넥터로 하위 폴더 결합(같은 구조 가정). SQLite는 제3자 ODBC | 4 | List Files + "Files in folder" 모드. Excel Reader는 파일당 시트 1개. SQLite JDBC 내장 |
| C3 한글 (10) | 4 | File Origin에서 코드 페이지 선택 ✔ (문자셋 추론 안 함, UTF-8은 BOM일 때만) | 3 | CSV Reader 인코딩 직접 입력(비공식 문서 근거) |
| C4 대용량 (10) | 2 | Import는 메모리 스냅샷. SQLite DirectQuery 가능 여부 확인 못함 | 4 | DB 노드가 쿼리를 쌓아 두고 Reader에서 한 번에 실행(지연 평가) |
| C5 에이전트 제어 (15) | 2 | 범용 CLI 없음. Authoring MCP(GA)는 모델링 전용 | 3 | 배치 모드(비공식 근거), Python 노드 API |
| C6 비SQL 탐색 (10) | 4 | 열 품질·분포·프로파일 ✔ (기본 1,000행, 전체로 전환 가능) | 4 | Node monitor Statistics, Data Explorer |
| C7 재사용성 (10) | 1 | 비공개. 포맷(PBIP/TMDL)과 아이디어만 | 2 | GPLv3(+예외). 코드 복사 시 라이선스 영향. 아이디어만 |
| C8 설치 용이성 (5) | 4 | Microsoft Store 또는 Download Center | 3 | 다운로드 전 이름·이메일 입력 |
| **합계 /100** | **59** | | **60** | |

## ldx에 가져올 것 (아이디어만, 코드 재사용 불가)

아키텍처
- Power Query Applied steps: 변환을 이름 붙은 단계의 재생 가능한 로그로 저장, 단계 선택 시 그 시점 미리보기
- 소스 설정(인코딩·구분자·줄바꿈)을 Source 단계에 저장해 나중에 수정
- KNIME 지연 DB 쿼리: 쿼리를 쌓고 마지막에 한 번 실행 → 2GB SQLite에 적합
- KNIME 경로를 데이터(테이블 열)로 다루기: 파일 목록을 먼저 표로 보여 주고 필터

기능
- 열 머리 아래 품질 막대(유효/오류/빈 값)와 분포 막대 ✔
- distinct(서로 다른 값 수)와 unique(한 번만 나온 값 수) 구분 표시 ✔
- 기본은 처음 1,000행으로 프로파일하고 사용자가 전체로 전환 ✔ → 대용량에 맞는 기본값
- 값 분포 막대를 눌러 필터, 텍스트 길이로 묶기 ✔
- CSV 인코딩은 추론 실패 가능성을 전제로 사용자가 바꿀 수 있게(Power BI도 추론 안 함) ✔
- Folder 결합 미리보기와 "같은 구조" 가정 경고

## 한계
- KNIME 배치 모드·CSV 인코딩은 공식 문서를 열지 못해 포럼·NodePit 근거. 해당 점수 불확실
- Power BI의 SQLite DirectQuery, MCP 라이선스는 확인 못함

✔ 메인 확인 출처: https://learn.microsoft.com/en-us/power-query/data-profiling-tools , https://learn.microsoft.com/en-us/power-query/connectors/text-csv
