"""RRSI-style gate for learned instincts: rule checks first, semantic judge last.

Mapping to RRSI (google-research/rrsi): learn_now.py = analyze+propose,
R* rules = critic screen (leakage/format), evidence/generalization = evaluate with a
noise floor, semantic judge = final check, select = promote/keep/prune.
Writes one structured JSON report; instinct status goes to <project>/instinct_status.json.
Usage: python eval_loop.py [--no-semantic] [project_name ...]
"""
import json, os, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

import importlib.util
_spec = importlib.util.spec_from_file_location(
    "instinct_cli", Path(__file__).resolve().parent / "continuous-learning-v2" / "scripts" / "instinct-cli.py")
icli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(icli)  # reuse ECC originals: parse_instinct_file, _trigger_keywords
sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor_wr"))
import semantic_review  # workflow-runner judge contract (copy pinned in vendor_wr/SOURCE.txt)

STORE = Path.home() / ".claude" / "ecc-homunculus"
MODEL, EFFORT = "claude-opus-5-5", "low"
REQUIRED = ("id", "trigger", "confidence", "domain", "source", "scope", "project_id", "project_name")
DOMAINS = {"code-style", "testing", "git", "debugging", "workflow", "file-patterns"}
DOC_EXT = re.compile(r"[^\s\"']+\.(pdf|hwp|hwpx|xlsx?|xlsm|csv)\b", re.I)
ANSWER_SIDE = re.compile(r"결과서|검토결과|정답|silver|gold[_ ]?label", re.I)
MIN_EVIDENCE_OBS = 3      # noise floor: pattern must be backed by >= 3 observations
JUDGE_RUNS = 3            # E1: promote only when all runs accept
EVIDENCE_SAMPLE = 8      # metadata lines per cited session in the judge packet (0 = ids/counts only)
JUDGE_SCHEMA = {  # mirrors semantic_review.valid_assessment
    "type": "object",
    "properties": {
        "verdict": {"enum": ["accept", "reject", "manual_review"]},
        "reason": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "integer"}, "minItems": 1},
    },
    "required": ["verdict", "reason", "evidence_ids"],
    "additionalProperties": False,
}
USER_RULES = ("예산서는 입력, 유사·중복 검토결과서는 정답 전용(입력 규칙에 섞지 않음); "
              "보고서 문장을 보고 규칙을 재구현하지 말고 원본 코드를 import; 실험 출력은 새 폴더에, 덮어쓰지 않음; "
              "전역/영구 설정 변경은 사용자 승인 필요.")


def parse(path: Path):
    parsed = icli.parse_instinct_file(path.read_text("utf-8"))
    if len(parsed) != 1:
        return None, ""
    fm = {k: str(v) for k, v in parsed[0].items() if k != "content"}
    return fm, parsed[0].get("content", "")


def rule_checks(fm, body, text, project_meta, sessions, others):
    r = {}
    r["R1_format"] = fm is not None and all(fm.get(k) for k in REQUIRED) and fm.get("domain") in DOMAINS \
        and _conf_ok(fm.get("confidence")) and fm.get("project_id") == project_meta["id"]
    r["R2_no_code_or_doc_text"] = "```" not in text and not any(len(l) > 300 for l in text.splitlines()) \
        and not DOC_EXT.search(text)
    r["R3_no_answer_side_rule"] = not ANSWER_SIDE.search(text)
    cited = {i for grp in re.findall(r"sessions?\s+((?:[0-9a-f-]{8,}(?:,\s*|\s+and\s+)?)+)", body)
             for i in re.findall(r"[0-9a-f-]{8,}", grp)}
    backed = {s for s in cited if sessions.get(s, 0) >= MIN_EVIDENCE_OBS}
    r["R4_evidence_sessions_exist"] = bool(cited) and cited == backed
    toks = _tokens(fm.get("trigger", "") if fm else "", project_meta["name"])
    dup = max((len(toks & o) / max(1, min(len(toks), len(o))) for o in others), default=0)
    r["R5_not_duplicate"] = dup < 0.6
    return r, {"cited_sessions": sorted(cited), "distinct_backed_sessions": len(backed), "max_trigger_overlap": round(dup, 2)}


def _conf_ok(v):
    try:
        return 0.3 <= float(v) <= 0.85
    except (TypeError, ValueError):
        return False


def _tokens(s, project_name=""):
    return icli._trigger_keywords(s) - icli._trigger_keywords(project_name.replace("-", " ").replace("_", " "))


def judge(text, evidence):
    packet = {"user_rules": USER_RULES, "evidence": evidence, "candidate_instinct": text}
    prompt = ("[ECC-AUTOMATED] " + semantic_review.JUDGE_PROMPT + "\nCandidate = a learned instinct for a coding agent. Reject it if it "
              "conflicts with user_rules; manual_review if not actionable or not supported by evidence.\n"
              + json.dumps(packet, ensure_ascii=False))
    try:
        r = subprocess.run(["claude", "--model", MODEL, "--effort", EFFORT, "--print", "--output-format", "json",
                        "--tools", "", "--json-schema", json.dumps(JUDGE_SCHEMA),
                        "--settings", '{"disableAllHooks":true}'],  # judge sessions must not be observed/captured
                       input=prompt.encode("utf-8"), capture_output=True, timeout=300, shell=(os.name == "nt"),
                       env=dict(os.environ, ECC_SKIP_OBSERVE="1"))
    except (subprocess.SubprocessError, OSError) as e:  # timeout/launch failure -> stays candidate
        return {"error": f"{type(e).__name__}: {e}"[:300]}
    try:
        out = json.loads(r.stdout.decode("utf-8", "replace"))
        return out.get("structured_output") or json.loads(out.get("result", "{}"))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {r.stderr.decode('utf-8', 'replace')[-300:]}"}


def evaluate_project(pdir: Path, meta: dict, semantic: bool):
    sessions, lines = {}, {}
    obs_files = sorted((pdir / "observations.archive").glob("*.jsonl")) + [pdir / "observations.jsonl"]  # E3
    for line in (l for f in obs_files if f.exists() for l in f.read_text("utf-8").splitlines()):
        try:
            rec = json.loads(line)
            s = rec.get("session", "")
        except ValueError:
            continue
        sessions[s] = sessions.get(s, 0) + 1
        lines.setdefault(s, []).append({k: str(rec[k])[:200] for k in ("event", "tool", "input") if k in rec})
    files = sorted((pdir / "instincts" / "personal").glob("*.md"))
    parsed = {f: parse(f) for f in files}
    results = []
    for f, (fm, body) in parsed.items():
        others = [_tokens(o[0].get("trigger", ""), meta["name"]) for g, o in parsed.items() if g != f and o[0]]
        text = f.read_text("utf-8")
        rules, info = rule_checks(fm, body, text, meta, sessions, others)
        hard_ok = all(rules.values())
        evidence = [{"event_id": i, "session": s, "observations": sessions.get(s, 0),
                     **({"sample": lines.get(s, [])[:EVIDENCE_SAMPLE]} if EVIDENCE_SAMPLE else {})}
                    for i, s in enumerate(info["cited_sessions"])]
        sems = [judge(text, evidence) for _ in range(JUDGE_RUNS)] if (semantic and hard_ok) else []  # semantic last
        valid = [s for s in sems if s is not None and semantic_review.valid_assessment(s, evidence)]  # rule check
        verdicts = [s["verdict"] for s in valid]
        sem = {"runs": sems, "verdicts": verdicts} if sems else None
        if not hard_ok:
            status = "rejected"
        elif "reject" in verdicts:
            status = "rejected"
        elif len(verdicts) == JUDGE_RUNS and set(verdicts) == {"accept"}:  # E1: all runs must agree
            status = "active"
        else:
            status = "candidate"
        results.append({"file": f.name, "status": status, "rules": rules, "evidence": info, "semantic": sem})
    (pdir / "instinct_status.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), "utf-8")
    return results


def main(argv):
    semantic = "--no-semantic" not in argv
    names = [a for a in argv if not a.startswith("--")]
    registry = json.loads((STORE / "projects.json").read_text("utf-8"))
    report = {"run_at": datetime.now(timezone.utc).isoformat(), "semantic": semantic, "projects": {}}
    for pid, meta in registry.items():
        if names and meta["name"] not in names:
            continue
        report["projects"][meta["name"]] = evaluate_project(STORE / "projects" / pid, meta, semantic)
    out = STORE / "eval_reports"
    out.mkdir(exist_ok=True)
    path = out / f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    for name, rs in report["projects"].items():
        for r in rs:
            failed = [k for k, v in r["rules"].items() if not v]
            print(f"{name} | {r['file']} | {r['status']} | failed={failed} | sessions={r['evidence']['distinct_backed_sessions']}")
    print("report:", path)


if __name__ == "__main__":
    main(sys.argv[1:])
