"""Claude Code PreToolUse guard: block whole-file Read of .pdf/.hwp/.hwpx (exit 2 = deny).

Reading these with the Read tool sends the whole file to the model API. Parse them locally
instead (e.g. govparse MCP) and pass only the needed excerpts.
"""
import json, sys
from pathlib import PurePath

BLOCKED = {".pdf", ".hwp", ".hwpx"}


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        path = (data.get("tool_input") or {}).get("file_path", "")
    except Exception:
        return 0
    if data.get("tool_name") == "Read" and PurePath(str(path)).suffix.lower() in BLOCKED:
        sys.stderr.buffer.write(("보안 차단: .pdf/.hwp/.hwpx 파일은 Read로 통째로 열 수 없습니다 "
                                 "(파일 전체가 외부로 전송됨). 로컬 파서로 필요한 부분만 추출하세요: " + str(path)).encode("utf-8"))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
