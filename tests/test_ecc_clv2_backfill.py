"""backfill.py replays past Claude Code / Codex transcripts with the live hooks' filters and record shapes.
Fixtures are synthetic; no real transcript is read."""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

_ECC = Path(__file__).resolve().parents[1] / "tools" / "ecc-clv2"
sys.path.insert(0, str(_ECC))
import backfill  # noqa: E402

SECRET = "SECRET-OUTPUT-BODY-NEVER-STORED"


def cc_line(kind, content, **extra):
    d = {"type": kind, "uuid": "u", "parentUuid": None, "sessionId": "sess-1", "timestamp": "2026-10-20T01:02:03.000Z",
         "cwd": extra.pop("cwd", "/no/such/dir"), "isSidechain": False, "entrypoint": "cli", "userType": "external",
         "message": {"role": kind, "content": content}}
    d.update(extra)
    return json.dumps(d, ensure_ascii=False)


def write_claude(dir_: Path):
    lines = [
        cc_line("user", "그게 아니라 원본 코드를 import 해야지 D:/x/예산서.hwpx"),                        # correction, doc path masked
        cc_line("user", "진행해"),                                                                         # plain prompt
        cc_line("user", "<task-notification>done</task-notification>"),                                     # injected
        cc_line("user", "아니라 자동", promptSource="sdk"),                                                 # automated turn
        cc_line("user", "아니라 메타", isMeta=True),                                                        # meta
        cc_line("user", "아니라 사이드", isSidechain=True, agentId="agent-1"),                               # subagent line
        cc_line("user", "[ECC-AUTOMATED] 아니라 판정", ),                                                  # learner/judge prompt
        cc_line("user", [{"type": "tool_result", "tool_use_id": "t1", "content": SECRET}], toolUseResult={"stdout": SECRET}),
        cc_line("assistant", [{"type": "text", "text": "assistant prose " + SECRET},
                              {"type": "tool_use", "id": "t1", "name": "Bash",
                               "input": {"command": "cat secret.txt | head -c 999", "description": "d"}},
                              {"type": "tool_use", "id": "t2", "name": "Write",
                               "input": {"file_path": "/a/b.py", "content": SECRET}}]),
        cc_line("assistant", [{"type": "tool_use", "id": "t3", "name": "Read", "input": {"file_path": "/s"}}], isSidechain=True, agentId="a"),
    ]
    (dir_ / "sess-1.jsonl").write_text("\n".join(lines) + "\n", "utf-8")
    sub = dir_ / "sess-1" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-abc.jsonl").write_text(cc_line("user", "아니라 서브에이전트", isSidechain=True, agentId="abc") + "\n", "utf-8")


def codex_line(kind, payload, ts="2026-10-21T05:06:07.000Z"):
    return json.dumps({"timestamp": ts, "ordinal": 0, "type": kind, "payload": payload}, ensure_ascii=False)


def write_codex(dir_: Path, subagent=False):
    meta = {"id": "thr-1", "cwd": "/no/such/dir", "thread_source": "subagent" if subagent else "user", "source": "cli"}
    lines = [
        codex_line("session_meta", meta),
        codex_line("response_item", {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "덮어쓰지 말고 새 폴더에 저장해"}]}),
        codex_line("response_item", {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "<environment_context>x</environment_context>"}]}),
        codex_line("response_item", {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "아니라 developer"}]}),
        codex_line("response_item", {"type": "custom_tool_call", "name": "exec", "input": "ls", "call_id": "c1"}),
        codex_line("response_item", {"type": "function_call", "name": "exec_command", "arguments": json.dumps({"cmd": ["echo", "hi"]}), "call_id": "c2"}),
        codex_line("response_item", {"type": "function_call_output", "call_id": "c2", "output": SECRET}),
        codex_line("response_item", {"type": "custom_tool_call", "name": "apply_patch", "input": "*** Begin Patch " + SECRET, "call_id": "c3"}),
    ]
    (dir_ / "rollout-2026-10-21T05-06-07-abc.jsonl").write_text("\n".join(lines) + "\n", "utf-8")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = self.tmp / "store"
        backfill.STORE = self.store
        self.claude = self.tmp / "claude"
        self.claude.mkdir()
        write_claude(self.claude)
        self.codex = self.tmp / "codex"
        self.codex.mkdir()
        write_codex(self.codex)

    def run_bf(self, *paths, dry=False):
        run = backfill.Run(dry, "", True)
        for p in paths:
            for f in sorted(Path(p).rglob("*.jsonl")):
                run.process(f, backfill.read_codex if f.name.startswith("rollout-") else backfill.read_claude)
        run.flush()
        return run

    def records(self, name):
        f = self.store / f"{name}.jsonl"  # cwd does not exist -> project 'global' -> store root
        return [json.loads(l) for l in f.read_text("utf-8").splitlines()] if f.exists() else []


class ClaudeFilters(Base):
    def test_only_human_corrections_are_kept(self):
        self.run_bf(self.claude)
        corr = self.records("corrections")
        self.assertEqual(len(corr), 1, corr)
        self.assertEqual(corr[0]["event"], "user_correction")
        self.assertEqual(corr[0]["timestamp"], "2026-10-20T01:02:03Z")  # original time, not now
        self.assertNotIn(".hwpx", corr[0]["text"])                     # doc path masked like the live hook

    def test_tool_uses_are_metadata_only(self):
        run = self.run_bf(self.claude)
        obs = self.records("observations")
        self.assertEqual([o["event"] for o in obs], ["tool_start", "tool_complete"] * 2)
        self.assertEqual({o["tool"] for o in obs}, {"Bash", "Write"})  # sidechain Read dropped
        blob = json.dumps(obs)
        self.assertNotIn(SECRET, blob)                                   # no tool output, no file content
        self.assertIn("cat secret.txt", blob)                            # command text (metadata) is kept
        self.assertEqual(run.counts["global"]["prompt_injected"], 2)  # <task-notification>, [ECC-AUTOMATED]

    def test_subagent_file_skipped(self):
        items = list(backfill.read_claude(self.claude / "sess-1" / "subagents" / "agent-abc.jsonl"))
        self.assertEqual(items, [])


class CodexFilters(Base):
    def test_codex_mapping_and_filters(self):
        self.run_bf(self.codex)
        corr = self.records("corrections")
        self.assertEqual([c["text"] for c in corr], ["덮어쓰지 말고 새 폴더에 저장해"])  # developer/env msgs dropped
        obs = [o for o in self.records("observations") if o["event"] == "tool_start"]
        self.assertEqual([o["tool"] for o in obs], ["Bash", "Bash", "Edit"])
        self.assertNotIn(SECRET, json.dumps(obs))  # apply_patch body and command output are not kept

    def test_codex_subagent_thread_skipped(self):
        d = self.tmp / "codex2"
        d.mkdir()
        write_codex(d, subagent=True)
        self.assertEqual(list(backfill.read_codex(next(d.glob("*.jsonl")))), [])


class DecisionLogs(Base):
    def test_curated_decisions_bypass_detector_and_keep_ids(self):
        d = self.tmp / "decisions"
        d.mkdir()
        (d / "studio.json").write_text(json.dumps({"recorded_on": "2026-10-21", "decisions": [
            {"id": "S-1", "status": "explicit_choice", "user_quote": "이게 가독성이 좋은데", "decision": "A 화면을 기준으로 쓴다."},
            {"id": "S-2", "status": "deferred", "decision": "설치 스크립트는 보류. " + "x" * 400}]}, ensure_ascii=False), "utf-8")
        (d / "dds.json").write_text(json.dumps({"recorded_on": "2026-10-14", "decisions": [
            {"id": "D-1", "status": "accepted", "decision": "곡선 커넥터 사용", "evidence": ["e1"]},
            {"id": "D-2", "status": "superseded", "decision": "직선 커넥터 사용"},
            {"id": "D-3", "status": "under_consideration", "decision": "대각선 검토 중"}]}), "utf-8")
        (d / "other.json").write_text(json.dumps({"schema": "x", "cases": [{"id": "c"}]}), "utf-8")
        run = backfill.Run(False, "", True)
        for f in sorted(d.glob("*.json")):
            run.process(f, backfill.read_decisions)
        run.flush()
        recs = self.records("corrections")
        self.assertEqual([r["decision_id"] for r in recs], ["D-1", "S-1", "S-2"])
        self.assertTrue(all(r["event"] == "user_decision" for r in recs))
        self.assertEqual(recs[1]["text"], "이게 가독성이 좋은데")          # user's words when recorded
        self.assertEqual(recs[2]["text"][:7], "설치 스크립트")              # else the decision itself
        self.assertLessEqual(len(recs[2]["decision"]), 300)
        self.assertEqual(recs[0]["timestamp"], "2026-10-14T00:00:00Z")
        self.assertEqual(run.counts["global"]["decision"], 3)
        self.assertEqual(run.counts["global"]["decision_skipped"], 2)  # superseded / under_consideration are not rules
        self.assertEqual(len(self.records("observations")), 0)


class ForcedProject(Base):
    def test_project_root_overrides_cwd_lookup(self):
        root = self.tmp / "my-proj"
        root.mkdir()
        run = backfill.Run(False, "", True, str(root))
        run.process(self.codex / next(self.codex.glob("*.jsonl")).name, backfill.read_codex)
        run.flush()
        reg = json.loads((self.store / "projects.json").read_text("utf-8"))
        (pid, meta), = reg.items()
        self.assertEqual((meta["name"], meta["root"], meta["remote"]), ("my-proj", str(root.resolve()), ""))
        self.assertTrue((self.store / "projects" / pid / "corrections.jsonl").exists())
        self.assertFalse((self.store / "corrections.jsonl").exists())  # nothing fell into global


class StateAndDryRun(Base):
    def test_rerun_adds_nothing(self):
        self.run_bf(self.claude, self.codex)
        n = (len(self.records("corrections")), len(self.records("observations")))
        run = self.run_bf(self.claude, self.codex)
        self.assertEqual(run.files["read"], 0)
        self.assertEqual(n, (len(self.records("corrections")), len(self.records("observations"))))

    def test_dry_run_writes_nothing(self):
        run = self.run_bf(self.claude, dry=True)
        self.assertFalse(self.store.exists())
        self.assertEqual(run.counts["global"]["correction"], 1)

    def test_cli_entrypoint(self):
        r = subprocess.run([sys.executable, "-I", str(_ECC / "backfill.py"), "--dry-run", "--no-state", "--regex", str(self.claude)],
                           env=dict(os.environ, ECC_CLV2_STORE_WIN=str(self.store)), capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("DRY RUN", r.stdout)
        self.assertIn("detector: regex", r.stdout)
        self.assertIn("corrections=    1", r.stdout)


if __name__ == "__main__":
    unittest.main()
