# Decision Labeling Studio

Human이 산출물을 직접 조작하며 비교하고, 판단·라벨·근거를 남기기 위한 검수 UI 모음입니다. 작성자: `chatgpt_gpt6`.

첫 반입은 DDS 검수 화면 두 패턴, 원본 `capture.html`·`review_index.html`을 외부 데이터셋으로 실행하는 두 UI, 의사결정 로그입니다. DDS renderer는 이 도구의 검수용 산출물로 재사용합니다.

## 실행

저장소 루트에서 `python -m http.server 8080 --bind 127.0.0.1`을 실행하고 `http://127.0.0.1:8080/`을 엽니다. 정적 HTML이므로 개별 파일로 열 수도 있지만 HTTP 실행을 권장합니다.

| 예제 | 재사용할 UI 동작 |
|---|---|
| [실제 도식 A/B 비교](examples/interactive-comparison/index.html) | 양쪽 iframe의 실제 접기·펼치기·Hover, 양쪽 전체 펼치기·접기, 좌우 교환 |
| [실제 도식 검수 대기열](examples/review-queue/index.html) | 사례 이동, 검수 기준, PASS·FAIL·보류, 의견, 브라우저 초안 복원, JSON 내보내기 |

A/B 예제는 두 역사적 DDS 스냅샷의 비교입니다. 후보의 우위나 최신 DDS 상태를 뜻하지 않습니다. 대기열의 4개 도식도 선택 당시의 재현용 스냅샷입니다. 각 사례의 파일·질문·ID를 바꿔 재사용할 수 있으나, 로컬 저장 키도 함께 바꿔 이전 초안과 섞이지 않게 해야 합니다. 도식은 DDS 소유 구현이며 여기서는 검수용 고정 입력으로 보존합니다.

두 정적 화면은 별개 패턴입니다. A/B 비교에는 판정 입력이 없고, 대기열은 한 번에 한 사례를 검수합니다. 대기열은 JSON을 다운로드하며 서버 DB나 채팅으로 자동 전송하지 않습니다.

## 다른 데이터셋 연결

Python 3.10 이상에서 별도 설치 없이 실행합니다. 아래 명령은 각각 독립 서버를 띄우며, 출력된 `http://127.0.0.1:포트/`를 엽니다.

```powershell
python studio_server.py --dataset datasets/capture-demo/dataset.json --votes .local/capture-votes.json
python studio_server.py --dataset datasets/record-demo/dataset.json --votes .local/record-votes.json
```

| 화면 | 유지한 검수 동작 | 데이터셋 |
|---|---|---|
| `ui/capture.html` | 원본 페이지와 후보 비교, 목표 영역 테두리, 확대, 후보·형식 선택, 사유 필수, 서버 JSON 저장 | `kind: capture`, 페이지 이미지, bbox, 후보 이미지 |
| `ui/review_index.html` | 항목 검색·필터, 원본 페이지·위치 이동, 근거 필드, 판정·사유, 저장·다음 항목 | `kind: record`, 항목·근거 후보, 페이지 이미지·위치 |

`--dataset`에 repo 밖의 JSON 경로를 지정해도 됩니다. 이미지 파일은 그 JSON이 있는 디렉터리 또는 하위에 두고 상대 경로로 연결합니다. [데이터 계약](datasets/CONTRACT.md)과 두 합성 예제를 참고하세요. 원래 앱의 13건·397행·고정 라벨·특정 부처·기존 DB 의존성을 가져오지 않았습니다. 합성 데이터셋은 각각 2건과 3건입니다.

기존 원문 변환·rhwp 뷰어·폴더 검색 기능 대신 **미리 렌더링한 페이지 이미지 API**를 연결했습니다. 실제 PDF/HWP 변환은 파서 프로젝트에서 수행한 후 결과를 이 계약으로 전달합니다. 이 서버에서 PDF/HWP 자체를 열거나 변환하지 않습니다. 서버는 로컬 주소에만 바인딩하며 계정·협업 동기화는 없습니다.

판정은 입력 JSON과 이미지들의 해시에 연결해 원자적으로 저장합니다. 입력이 달라지면 기존 판정 파일을 재사용하지 않으며, 새 `--votes` 경로를 사용해야 합니다. 초안과 확정 저장은 구분됩니다. 자동 실행 테스트에서 만든 판정은 테스트 디렉터리에만 보관합니다. 실행 중 변경된 파일은 재시작 후 새 판정 파일로 검수하세요.

## HWP 원본 충돌 검수 (`kind: conflict`)

교차검증 충돌 사례를 HWP 원본과 함께 검수합니다. 원본은 브라우저에서 rhwp(@rhwp/core, MIT)로 직접 그리고, 감사 카드를 누르면 카드의 XPath(`location`)와 인용이 **같은 위치를 가리킬 때만** 해당 쪽으로 이동·강조합니다. 어긋나면 `위치 확인 불가 — 이유`를 표시합니다.

```powershell
python conflict_server.py --dataset <human_conflicts.json> --votes .local/conflict-votes.json --rhwp <node_modules/@rhwp/core>
```

- 데이터: 사례 배열(`pair_id`, `new_business`, `comparison_business`, `evidence.sources[{path, sha256}]`, `audit_cards[{title, quote, location}]`). [계약](datasets/CONTRACT.md#conflict). 원본 HWP와 rhwp 바이너리는 repo에 넣지 않습니다.
- 원본은 sha256이 맞을 때만 내보냅니다. 판정은 데이터셋 해시에 묶인 `studio-votes/v1` JSON에 원자적으로 저장합니다(`decided_by: human`, 원본 해시 포함).
- 시험: `python -m unittest discover -s tests`, `node tests/hwp_locate.test.mjs`. 출처·비교·검증: [provenance/conflict-import-20261021.json](provenance/conflict-import-20261021.json).

## 의사결정 기록

[decisions/dds](decisions/dds/)에는 회고적으로 정리한 제품 결정, 실험 결정, 채팅의 Human 답변을 기록한 후속 JSON을 보존합니다. 파일에 있는 상태·작성 방식·한계는 원문 그대로 유지합니다. Agent 검증과 Human 판정은 별개이며, 경로로 참조하는 모든 과거 산출물을 함께 올린 것은 아닙니다.

2026-10-16 사용자의 명시적 의사결정 로그 업로드 요청에 따라 이 다섯 로그를 선별했습니다. 모든 과거 원장·실행 로그를 일괄 공개하는 정책으로 확대하지 않습니다. PDF·HWP 원문이나 그 변환 문서는 포함하지 않았습니다. 이 README는 새로 작성한 사용 설명입니다.

## 선별·검증

[선별 기록](provenance/selection-20261016.json), [원본·반입 해시](provenance/import-manifest.json), [브라우저 검증](provenance/browser-validation.json)을 참고하세요. Main이 원본 두 조작 화면과 정적 비교 후보 세 개의 렌더 이미지를 직접 읽었습니다. 정적 이미지 대조보다 실제 도식 조작을 선호한다는 사용자 지시에 따라 정적 후보는 제외했습니다. 반입한 화면도 재렌더링해 직접 확인했습니다. 이 IMAGE READ는 새 Human 승인 판정이 아닙니다.

Windows Edge에서 네 UI의 조작과 저장을 확인했습니다. 다른 브라우저·모바일 전체 UX를 검증한 결과는 아닙니다. API 회귀 테스트는 `python -m unittest discover -s tests`로 실행합니다. 브라우저 테스트는 Playwright가 있는 환경에서 `node tests/browser.cjs`로 실행합니다. `PLAYWRIGHT_MODULE`(모듈명 또는 경로), `EDGE_PATH`(선택), `PYTHON`(선택), `STUDIO_EVIDENCE`(결과 위치)를 환경변수로 지정할 수 있습니다. 원본 UI는 기존 작성자 표기를 유지하고, 범용화·서버·검증은 `chatgpt_gpt6`가 작성했습니다.

현재 별도 오픈소스 라이선스를 부여하지 않았습니다. 기존 DDS 스냅샷은 해당 원본의 권리·조건을 따릅니다.
