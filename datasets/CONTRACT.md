# 외부 데이터셋 계약

작성자: `chatgpt_gpt6`. 원문에서 변환한 문서가 아닌 새 API 설명입니다.

`studio_server.py --dataset /path/to/dataset.json --votes /path/to/votes.json`으로 지정합니다. 예제 JSON을 복사해 항목과 상대 이미지 경로를 교체하세요. 파일명이나 경로에서 업무 의미를 추론하지 않습니다.

공통 필드:

- `kind`: `capture` 또는 `record`. 계약 예정(구현 전): [`grid_compare_triage`](#grid_compare_triage).
- `title`, `question`: 화면 제목과 판정 질문. 문자열.
- `pages`: JSON 디렉터리 기준 이미지 상대 경로 배열. PNG/JPEG/WebP/SVG. 한 페이지당 한 이미지이며 최소 1개.
- `cases`: 최소 1개. `id`는 중복 없는 영문·숫자·`_`·`-` 문자열, `label`은 표시명, `page`는 `pages`의 1부터 시작하는 번호.

`capture` 항목:

- `source_page_size: [width, height]`: 원본 페이지의 좌표계 크기.
- `source_bbox: [x0, y0, x1, y1]`: 같은 좌표계의 목표 영역. 좌상단 원점, 유한한 값, 페이지 범위 내의 양수 면적.
- `candidates: [{"raw": "candidate.png", "composite": "rendered.png"}]`: 둘 중 하나 이상. 배열 순서로 후보 번호를 부여. 후보가 없으면 빈 배열을 사용하며 오류·누락을 숨기지 않음.

`record` 항목:

- `group`: 기관 등 그룹 표시명(선택).
- `priority`: 우선 검수 여부(기본 true).
- `match_pages`: 해당 항목 근거가 있는 페이지 번호 배열. 기본은 `[page]`. 자동 검색 결과로 단정하지 않고 제공된 연결을 표시함.
- `fields: [{"label":"분류", "value":"시연용", "unit":""}]`: 항목 옆의 참고 필드(선택).
- `candidates: [{"raw_name":"원문 명칭", "source_path":"page.svg", "anchor":"page 1 / section A"}]`: 원문 근거 후보(선택). 문자열을 자동 정답이나 Human 승인으로 취급하지 않음.

이전 UI의 내부 API 호환을 위해 `excel_row`는 `cases` 배열의 1부터 시작하는 인덱스, `excel_name`은 `label`로 매핑됩니다. Excel 파일은 필요 없습니다. 저장 판정에는 외부 `case_id`도 남습니다. 순서 변경도 새 입력 리비전입니다.

API는 화면용 `GET /api/cases`, 페이지용 `GET /api/source-page`, capture 후보·crop API, record의 `GET /api/source-preview`를 제공합니다. 저장은 capture의 `POST /api/decision`, record의 `POST /api/vote`입니다. 데이터셋별 선택지는 기존 UI와 같습니다. 판정불가 사유와 record의 상이 사유는 필수입니다.

저장 파일은 `schema: studio-votes/v1`, 입력·이미지 결합 해시인 `input_sha256`, `decisions` 또는 `votes`를 포함합니다. `submitted_via: local_review_ui`는 전달 경로이며 실제 Human 신원 인증을 의미하지 않습니다. 입력 변경 시 파일을 덮어 재활용하지 말고 새 `--votes`를 지정하세요. 이 계약은 협업 중 충돌 병합이나 사용자 인증을 제공하지 않습니다.

<a id="grid_compare_triage"></a>
## grid_compare_triage 데이터셋 (계약 예정, 구현 전)

상태: 이름과 정의만 정한 단계. 화면·서버 구현과 필드 형식은 아직 없음. 이름은 바뀔 수 있음.

정의: 사람이 소스별 grid끼리 대조해 같음·다름·한쪽에만 있음 패턴을 파악하고, 범위·의미·대응·정제 여부를 고려해 그 패턴에 해당하는 레코드 집합을 조건 단위로 처리(현재 라벨: 보존·정제 후 보존·폐기·보류, 바뀔 수 있음)할지 결정하며, 그 근거로 일관된 결정을 하도록 보조하는 스튜디오 화면 유형.

- 데이터셋: 짝 저장소 [goodand/tabular-compare-engine](https://github.com/goodand/tabular-compare-engine)(화면 없는 계산 엔진)이 이 계약 형식으로 만들어 줄 예정. 형식은 그때 이 절에 정한다.
- 판정 단위: 레코드 한 행이 아니라 조건(규칙)과 그 조건에 해당하는 레코드 집합.
- 판정 저장: 기존 규칙과 같다. 입력 해시(`input_sha256`)에 묶인 votes, 입력이 바뀌면 새 `--votes`.
- 이름 근거: 이름만 보여 주고 설명하게 한 검증(Sonnet·Haiku × 개발자·최종 사용자·UI/UX 설계자 관점 × 3회). 사람 관점 12건 오독 0, 개발자 관점 6건 중 2건이 "시뮬레이션 격자 출력 비교"로 읽힘. 화면 유형 이름은 사람이 읽으므로 사람 관점 기준으로 채택.

