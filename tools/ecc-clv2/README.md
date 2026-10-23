# tools/ecc-clv2 — HumanMessage 기반 교훈 학습·스킬 진화

작성자: Claude (Harness 담당 세션), 2026-10-21~23. 출처: `D:/web_chat_gpt/ecc-continuous-learning-trial-20261021` (실험 기록·실측값 포함) (해시는 `PROVENANCE.json`).

에이전트가 세션마다 잊는 교훈을 **사용자의 정정 발화**에서 모아, 규칙 검사로 거르고(LLM 판정은 선택·기본 꺼짐) 메모리로 올리는 파이프라인입니다. ECC(everything-claude-code) `continuous-learning-v2`의 관찰 훅은 도구 호출만 보기 때문에 실사용 교훈이 잡히지 않는 문제를 메웁니다.

## 구성

| 파일 | 역할 | 훅 |
|---|---|---|
| `capture_correction.py` | 사용자 프롬프트에서 정정 문장을 **규칙**으로 감지해 ≤300자 저장. Kiwi 형태소 규칙(상주 서버) → 정규식 폴백 | `UserPromptSubmit` |
| `kiwi_server.py` | localhost:48791 Kiwi(`cong`) 상주 서버. `--stop`으로 종료 | Task Scheduler |
| `observe_meta.py` | (선택) ECC `observe.sh` 앞단 필터: 도구 출력 제거, 경로·명령 앞 200자만 기록 | `PreToolUse`/`PostToolUse` |
| `block_doc_read.py` | `.pdf/.hwp/.hwpx` 통째 Read 차단(exit 2) | `PreToolUse` (Read) |
| `learn_now.py` | 관찰+정정 기록 → Claude(Opus, effort low)로 instinct 추출. 자동 세션은 훅을 끔 | 수동/`auto_learn` |
| `eval_loop.py` | 게이트: R1 형식·R2 코드/문서 금지·R3 정답측 규칙 금지·R4 인용 세션 실존·R5 중복 → 통과분만 3회 LLM 판정(모두 accept일 때 active) | 〃 |
| `auto_learn.py` | 새 관찰 ≥20건일 때 learn→eval→publish. 기본은 규칙 게이트만(LLM 판정은 `ECC_LEARN_SEMANTIC=1`일 때만). 규칙 통과분은 digest로 사람 검토 | `Stop` (async) |
| `platform_compat.py` | OS 분기를 모은 유일한 파일: 저장소 경로, bash 경로·경로 형식, 파일 잠금(msvcrt/fcntl), Kiwi 서버 깨우기(Task Scheduler/launchd) | — |
| `vendor_wr/semantic_review.py` | 판정 계약(accept/reject/manual_review + evidence_ids) — workflow-runner 원본 사본 | — |

실사용 교훈(도메인 규칙)과 메타 교훈(도구 습관)은 분리합니다. 이 패키지가 자동 승격하는 것은 메타 교훈뿐이며, 실사용 교훈은 사람이 확인한 뒤 프로젝트 메모리에 둡니다.

## 요구사항

- Windows 또는 macOS, Python 3.12 이상, `kiwipiepy` 0.24 (`pip install kiwipiepy`), Claude Code CLI(`claude`)
- ECC `continuous-learning-v2` 스킬 디렉터리(`observe_meta`·`eval_loop`가 원본 `observe.sh`, `instinct-cli.py`를 호출): `upstream/continuous-learning-v2/`에 사본이 있음(MIT, PROVENANCE.json). 다른 위치를 쓰려면 `ECC_CLV2_SKILL_DIR`
- bash: Windows는 Git Bash(`ECC_GIT_BASH`, 기본 `C:\Program Files\Git\bin\bash.exe`), macOS는 시스템 bash(`ECC_GIT_BASH`로 바꿀 수 있음)

## 설치 (전역 설정 변경은 사용자 승인 후)

설치 스크립트(설치본 복사 + 커밋 해시 기록)는 보류 중입니다(결정 STUDIO-ECC-005). 그때까지는 아래를 손으로 설정합니다.

`~/.claude/settings.json`의 `hooks`에 아래를 추가합니다. `PY`는 kiwipiepy가 설치된 python.exe 절대 경로, `L`은 이 폴더(`tools/ecc-clv2`) 절대 경로. 현재 실행 중인 훅은 `~/.claude/ecc-clv2` 사본을 가리키며(결정 STUDIO-ECC-003), 저장소 사본으로 바꾸는 것은 별도 결정입니다.

```json
{"hooks": {
  "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "\"PY\" -X utf8 -I \"L/capture_correction.py\"", "timeout": 10}]}],
  "PreToolUse": [{"matcher": "Read", "hooks": [{"type": "command", "command": "\"PY\" -X utf8 -I \"L/block_doc_read.py\"", "timeout": 10}]},
                 {"matcher": "*", "hooks": [{"type": "command", "command": "\"PY\" -I \"L/observe_meta.py\" pre", "async": true, "timeout": 30}]}],
  "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "\"PY\" -I \"L/observe_meta.py\" post", "async": true, "timeout": 30}]}],
  "Stop": [{"hooks": [{"type": "command", "command": "\"PY\" -X utf8 -I \"L/auto_learn.py\"", "async": true, "timeout": 1800}]}]
}}
```

Kiwi 서버 수명(사용자 요구: 상시 상주, 주 1회 자동 종료):

```bat
schtasks /Create /F /SC ONLOGON /TN "\ECC_KiwiStart" /TR "PYW -X utf8 -I L\kiwi_server.py"
schtasks /Create /F /SC WEEKLY /D SUN /ST 04:00 /TN "\ECC_KiwiWeeklyStop" /TR "PYW -X utf8 -I L\kiwi_server.py --stop"
```

`PYW`는 `pythonw.exe`. 훅은 서버가 없으면 정규식으로 처리한 뒤 `ECC_KiwiStart` 작업을 실행해 되살립니다(훅의 자식 프로세스는 훅 종료와 함께 죽으므로 Task Scheduler를 씁니다).

macOS에서는 훅 명령의 `PY`에 kiwipiepy가 설치된 `python3` 절대 경로를 넣습니다. Kiwi 서버 상주는 launchd가 맡습니다. `~/Library/LaunchAgents/ECC_KiwiStart.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>ECC_KiwiStart</string>
  <key>ProgramArguments</key><array><string>PY</string><string>-X</string><string>utf8</string><string>-I</string><string>L/kiwi_server.py</string></array>
  <key>RunAtLoad</key><true/>
</dict></plist>
```

`launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ECC_KiwiStart.plist`로 등록합니다. 서버가 죽으면 훅이 `launchctl kickstart`로 되살립니다. 주 1회 종료가 필요하면 `--stop`을 실행하는 plist를 `StartCalendarInterval`(일요일 04:00)로 하나 더 둡니다. 저장소가 Desktop·Documents 아래에 있으면 처음 실행할 때 macOS 폴더 접근 권한 창이 뜰 수 있습니다.

환경변수: `ECC_CLV2_STORE_WIN`/`ECC_CLV2_STORE`(저장소, 모든 스크립트가 같은 값을 씀, 기본 `~/.claude/ecc-homunculus`), `ECC_LEARN_DIGEST`, `ECC_LEARN_HABITS`(출력 메모리 파일. 비워 두면 원래 Windows PC의 메모리 폴더가 있을 때만 그곳, 없으면 저장소 폴더에 씀), `ECC_KIWI_START_TASK`.

## 실측값 (2026-10-23, Windows 11)

- 훅 지연: Kiwi 서버 up 110–130ms, 폴백(정규식+작업 실행) ~225ms. Kiwi 자체는 로드 0.6s, 호출당 0.09ms
- 판정 안정성: 증거 표본 없이 1회 판정은 흔들림 → 3회 모두 accept일 때만 승격
- 자동 세션 자기관찰 오염: `--settings {"disableAllHooks":true}` + `[ECC-AUTOMATED]` 표식으로 차단

## 테스트

```bat
python -m unittest discover -s tests -p "test_ecc_clv2_*.py"
```

ECC 스킬 디렉터리가 없으면 `eval_loop`/`auto_learn` 테스트는 건너뜁니다(`upstream/` 사본이 있으면 실행). Kiwi 테스트는 서버를 띄웠다가 끝에 반드시 내립니다.

## 검증 원칙

사람 판정이 기준이고, 재현성은 규칙이 보장합니다. LLM 판정은 정확성·재현성 모두 더 낫지 않아 기본으로 쓰지 않습니다. 사람이 digest에서 내린 결정의 근거는 기록해 두었다가 규칙으로 옮깁니다(사람 패턴의 규칙화).

## 한계

- 정정 감지는 규칙 기반이라 표지어 없는 정정은 놓칩니다.
- 자동 승격 대상은 메타 교훈뿐이고, 실사용 교훈은 digest를 사람이 읽고 반영합니다.
- 저장소 전체 단일 잠금(observe_meta)이라 다중 세션 과부하 시 메타데이터 일부가 버려질 수 있습니다.
