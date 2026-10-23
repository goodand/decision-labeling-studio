"""Breaks found by the adversarial check (Haiku, 2026-10-24), frozen as tests. Each class names the claim
it attacks; every case here failed on b492fae. Fixtures are synthetic."""
import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

_ECC = Path(__file__).resolve().parents[1] / "tools" / "ecc-clv2"
if not (os.environ.get("ECC_CLV2_SKILL_DIR") or (_ECC / "upstream" / "continuous-learning-v2").exists()):
    raise unittest.SkipTest("ECC continuous-learning-v2 upstream copy missing (set ECC_CLV2_SKILL_DIR)")
sys.path.insert(0, str(_ECC))
sys.path.insert(0, str(_ECC / "vendor_h2"))
import backfill, observe_meta, repeat_instr, capture_correction as cc, leak_guard  # noqa: E402


def cc_line(sess, sec, text):
    return json.dumps({"type": "user", "sessionId": sess, "timestamp": f"2026-10-22T00:00:0{sec}.000Z", "cwd": "/none",
                       "isSidechain": False, "entrypoint": "cli", "message": {"role": "user", "content": text}},
                      ensure_ascii=False) + "\n"


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        backfill.STORE = self.tmp / "store"
        self.src = self.tmp / "src"
        self.src.mkdir()
        self.f = self.src / "f.jsonl"
        self.f.write_text(cc_line("S1", 1, "그게 아니라 a") + cc_line("S1", 2, "그게 아니라 b"), "utf-8")

    def run_bf(self, since="", until="", rebuild=False, use_state=True):
        r = backfill.Run(False, since, use_state, rebuild_repeat=rebuild, until=until)
        for f in sorted(self.src.glob("*.jsonl")):
            r.process(f, backfill.read_claude)
        r.flush()
        return r

    def corrections(self):
        p = backfill.STORE / "corrections.jsonl"
        out = []
        for l in (p.read_text("utf-8").splitlines() if p.exists() else []):
            try:
                r = json.loads(l)
            except ValueError:
                continue  # corrupt lines planted by test_G
            if isinstance(r, dict):
                out.append(r)
        return out


class Idempotent(Store):
    def test_R1_growing_file_adds_only_the_new_line(self):
        self.run_bf()
        with self.f.open("a", encoding="utf-8") as fh:
            fh.write(cc_line("S1", 3, "그게 아니라 c"))
        self.run_bf()
        self.assertEqual(len(self.corrections()), 3)

    def test_R2_window_then_full_run_adds_nothing(self):
        self.run_bf(since="2026-10-22", until="2026-10-23")
        self.run_bf()
        self.assertEqual(len(self.corrections()), 2)

    def test_R6_rebuild_repeat_never_appends_records(self):
        self.run_bf()
        with self.f.open("a", encoding="utf-8") as fh:
            fh.write(cc_line("S1", 3, "그게 아니라 c"))
        self.run_bf(rebuild=True)
        self.run_bf(rebuild=True, use_state=False)
        self.assertLessEqual(len(self.corrections()), 3)


class LiveGuard(Store):
    def test_R3_live_record_in_root_archive_blocks_replay(self):
        arch = backfill.STORE / "observations.archive"
        arch.mkdir(parents=True)
        (arch / "o.jsonl").write_text(json.dumps({"event": "tool_start", "session": "S1"}) + "\n", "utf-8")
        self.run_bf()
        self.assertEqual(self.corrections(), [])


class MetadataOnly(unittest.TestCase):
    def test_R4_kept_input_fields_are_capped(self):
        s = observe_meta.sanitize({"tool_input": {"description": "x" * 900, "url": "https://e.com/" + "q" * 1200,
                                                  "pattern": "p" * 500}})["tool_input"]
        self.assertTrue(all(len(v) <= observe_meta.CMD_LIMIT for v in s.values()), {k: len(v) for k, v in s.items()})

    def test_R4_heredoc_body_is_not_stored(self):
        s = observe_meta.sanitize({"tool_input": {"command": "cat > a.py <<'EOF'\nSECRET_FILE_BODY\nEOF"}})["tool_input"]
        self.assertNotIn("SECRET_FILE_BODY", s["command"])
        self.assertEqual(s["command"], "cat a.py")  # allowlist (STUDIO-ECC-019): a plain file name is metadata (like file_path); the heredoc is not

    def test_R4_multiline_command_keeps_first_line_only(self):
        s = observe_meta.sanitize({"tool_input": {"command": "python3 - <<X\nimport os\nprint(os.environ)\nX"}})["tool_input"]
        self.assertNotIn("os.environ", s["command"])

    def test_R5_repeated_phrase_is_capped_and_long_tokens_dropped(self):
        idx = repeat_instr.Index()
        for s in ("a", "b", "c"):
            idx.add(s, "장단점 설명 " + "Q9" * 400 + " sk_live_" + "A1" * 30)
        recs = repeat_instr.records(idx, min_sessions=3)
        self.assertTrue(recs)
        self.assertTrue(all(len(r["phrase"]) <= cc.MAX_CHARS for r in recs))
        self.assertFalse(any("Q9Q9" in r["phrase"] or "sk_live" in r["phrase"] for r in recs))

    def test_docx_and_pptx_paths_are_masked(self):
        rec = cc.make_record("s", "/x", "아니라 D:/a/보고서.docx 와 b.pptx 봐")
        self.assertNotIn(".docx", rec["text"])
        self.assertNotIn(".pptx", rec["text"])


class AutoLearnException(unittest.TestCase):
    def test_R8_learn_exception_is_recorded_and_cooled_down(self):
        import auto_learn
        store = Path(tempfile.mkdtemp())
        auto_learn.STORE = store
        auto_learn.DIGEST = store / "d.md"
        auto_learn.HABITS = store / "h.md"
        pdir = store / "projects" / "p1"
        (pdir / "instincts" / "personal").mkdir(parents=True)
        (store / "projects.json").write_text(json.dumps({"p1": {"id": "p1", "name": "demo"}}), "utf-8")
        (pdir / "observations.jsonl").write_text("\n".join(json.dumps({"session": "s"}) for _ in range(30)), "utf-8")
        calls = []

        def boom(p, m):
            calls.append(1)
            raise FileNotFoundError("claude")
        with mock.patch.object(auto_learn.learn_now, "run", boom), mock.patch.dict(os.environ):
            os.environ.pop("ECC_LEARN_SEMANTIC", None)
            auto_learn.main([])
            auto_learn.main([])
        self.assertEqual(len(calls), 1)
        self.assertIn("FileNotFoundError", (pdir / ".auto_learn_error.json").read_text("utf-8"))


class OriginRound2(Store):
    """Round 2: origin was file-path + position. Content-based origins must survive these."""
    def test_A_truncate_then_regrow(self):
        self.run_bf()
        self.f.write_text(cc_line("S1", 1, "그게 아니라 a") + cc_line("S1", 3, "그게 아니라 X") + cc_line("S1", 4, "그게 아니라 Y"), "utf-8")
        self.run_bf()
        texts = sorted(r["text"] for r in self.corrections())
        self.assertEqual(texts, sorted(["그게 아니라 a", "그게 아니라 b", "그게 아니라 X", "그게 아니라 Y"]))

    def test_B_rewrite_same_size_is_seen(self):
        self.run_bf()
        self.f.write_text(cc_line("S1", 1, "그게 아니라 c") + cc_line("S1", 2, "그게 아니라 d"), "utf-8")
        self.run_bf()
        self.assertEqual(len(self.corrections()), 4)

    def test_C_copied_file_adds_nothing(self):
        self.run_bf()
        (self.src / "g.jsonl").write_text(self.f.read_text("utf-8"), "utf-8")
        self.run_bf()
        self.assertEqual(len(self.corrections()), 2)

    def test_D_insert_at_top_keeps_everything_once(self):
        self.run_bf()
        self.f.write_text(cc_line("S1", 0, "그게 아니라 Z") + self.f.read_text("utf-8"), "utf-8")
        self.run_bf()
        self.assertEqual(sorted(r["text"][-1] for r in self.corrections()), ["Z", "a", "b"])

    def test_E_two_runs_flushed_late_do_not_double(self):
        r1, r2 = backfill.Run(False, "", True), backfill.Run(False, "", True)
        for r in (r1, r2):
            r.process(self.f, backfill.read_claude)
        r1.flush()
        r2.flush()
        self.assertEqual(len(self.corrections()), 2)

    def test_G_corrupt_store_lines_do_not_crash(self):
        backfill.STORE.mkdir(parents=True)
        (backfill.STORE / "corrections.jsonl").write_text('"origin"\n{"origin": {"a": 1}}\n["origin"]\nnot json\n', "utf-8")
        self.run_bf()
        self.assertEqual(len([r for r in self.corrections() if r.get("source") == "backfill"]), 2)


class MetadataRound2(unittest.TestCase):
    def san(self, cmd):
        return observe_meta.sanitize({"tool_input": {"command": cmd}})["tool_input"]["command"]

    def test_H1_inline_script_body_is_not_stored(self):
        self.assertNotIn("SECRET_BODY", self.san("python3 -c \"print('SECRET_BODY')\""))

    def test_H2_H3_cr_and_unicode_line_separators_split(self):
        self.assertNotIn("SECRET_BODY", self.san("cat > a.py <<'EOF'\rSECRET_BODY\rEOF"))
        self.assertNotIn("SECRET_BODY", self.san("cat > a.py <<'EOF'\u2028SECRET_BODY\u2028EOF"))

    def test_H4_H5_credentials_in_url_and_env_are_masked(self):
        self.assertNotIn("Zx9qLm2pW8", self.san("psql postgres://admin:Zx9qLm2pW8@db.local/x"))
        self.assertNotIn("p@ss!w0rd", self.san("PASSWORD=p@ss!w0rd ./run.sh"))
        self.assertIn("psql", self.san("psql postgres://admin:Zx9qLm2pW8@db.local/x"))

    def test_I_key_shaped_tokens_never_become_phrases(self):
        idx = repeat_instr.Index()
        for s in ("a", "b", "c"):
            idx.add(s, "AKIAXXXXXXXXXXXXXXXX 이거 항상 기억해줘 sk_live_abc123def456")
        blob = json.dumps(repeat_instr.records(idx, min_sessions=3), ensure_ascii=False).lower()
        self.assertNotIn("akia", blob)
        self.assertNotIn("sk_live", blob)


class CommandAllowlist(unittest.TestCase):
    """Round 3: a blocklist of secret patterns kept leaking. Commands are reduced to their SHAPE:
    program names, subcommand words, flag names, and shell separators. No value survives."""
    SECRETS = ['curl -H "Authorization: Bearer ABCSECRET123" https://api.x/y', "curl -H 'Authorization: token ABCSECRET123' u",
               "app --password ABCSECRET123", "app --password=ABCSECRET123", "app --token=ABCSECRET123",
               "api_key=ABCSECRET123 ./run", "export DB_CONN=ABCSECRET123", 'PASSWORD="my ABCSECRET123 pass" ./run',
               "gh auth login --with-token ghp_ABCSECRET123", "aws configure set aws_access_key_id AKIAABCSECRET123",
               "curl 'https://x/y?access_token=ABCSECRET123'", "psql postgres://admin:p@ABCSECRET123@db.local",
               "node -p \"process.env.ABCSECRET123\"", "bash -lc 'echo ABCSECRET123'", 'python3 -c"print(1)" ABCSECRET123',
               'powershell -Command "Get-Secret ABCSECRET123"']

    def san(self, cmd):
        return observe_meta.sanitize({"tool_input": {"command": cmd}})["tool_input"]["command"]

    def test_no_value_survives(self):
        for c in self.SECRETS:
            self.assertNotIn("abcsecret123", self.san(c).lower(), c)

    def test_shape_is_kept(self):
        self.assertEqual(self.san("git -c user.name=x commit -m 'msg'"), "git -c commit -m")
        self.assertEqual(self.san("echo $((1<<2)) && make test"), "echo && make test")
        self.assertEqual(self.san("curl -H 'X: y' https://api.x/y"), "curl -H")
        self.assertEqual(self.san("python3 -m pytest tests -q"), "python3 -m pytest tests -q")


class OriginRound3(Store):
    def test_1a_two_identical_tool_calls_in_one_message_are_two_events(self):
        line = {"type": "assistant", "sessionId": "S9", "timestamp": "2026-10-22T00:00:01.000Z", "cwd": "/none",
                "isSidechain": False, "entrypoint": "cli", "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "git status"}},
                    {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "git status"}}]}}
        self.f.write_text(json.dumps(line) + "\n", "utf-8")
        self.run_bf()
        obs = [json.loads(l) for l in (backfill.STORE / "observations.jsonl").read_text("utf-8").splitlines()]
        self.assertEqual(sum(o["event"] == "tool_start" for o in obs), 2)

    def test_1e_lone_surrogate_does_not_abort_the_run(self):
        bad = json.dumps({"type": "user", "sessionId": "S1", "timestamp": "2026-10-22T00:00:01.000Z", "cwd": "/none",
                          "isSidechain": False, "entrypoint": "cli", "message": {"role": "user", "content": "그게 아니라 \ud83d 깨진 문자"}})
        self.f.write_text(bad + "\n" + cc_line("S1", 2, "그게 아니라 b"), "utf-8")
        self.run_bf()
        self.assertGreaterEqual(len(self.corrections()), 1)

    def test_3b_concurrent_runs_keep_both_states(self):
        g = self.src / "g.jsonl"
        g.write_text(cc_line("S2", 1, "그게 아니라 g"), "utf-8")
        r1, r2 = backfill.Run(False, "", True), backfill.Run(False, "", True)
        r1.process(self.f, backfill.read_claude)
        r2.process(g, backfill.read_claude)
        r1.flush()
        r2.flush()
        state = json.loads((backfill.STORE / "backfill_state.json").read_text("utf-8"))
        self.assertEqual({Path(k).name for k in state}, {"f.jsonl", "g.jsonl"})


class KeyShapeRound3(unittest.TestCase):
    def test_ordinary_words_survive(self):
        kept = repeat_instr.words("v2beta1workflow sonnet45latest gpt4turbo2024 sk_learn xoxo eyjournal akiapowerful")
        self.assertEqual(kept, ["v2beta1workflow", "sonnet45latest", "gpt4turbo2024", "sk_learn", "xoxo", "eyjournal", "akiapowerful"])

    def test_real_key_shapes_still_dropped(self):
        # assembled at run time: literal credential-shaped strings trip GitHub push protection
        fake = ["AKIA" + "Z9Y8X7W6V5U4T3S2", "sk_" + "live_" + "q1w2e3r4" * 3, "ghp_" + "a1b2c3d4e5" * 4]
        kept = repeat_instr.words(" ".join(fake) + " 기억해")
        self.assertEqual(kept, ["기억해"])


class SpawnStorm(unittest.TestCase):
    """Measured 2026-10-24: 20 classifications with the Kiwi server down spawned 20 servers, each loading the
    ~100MB model (likely what overheated the machine during the first backfill). At most one spawn per window."""
    def test_classifications_with_server_down_spawn_at_most_once(self):
        spawned = []
        with mock.patch.object(cc, "_tokens_from_server", side_effect=OSError("down")), \
             mock.patch.object(cc.pc, "start_detached", lambda argv, task: spawned.append(1)), \
             mock.patch.object(cc, "SPAWN_MARK", Path(tempfile.mkdtemp()) / "kiwi-spawn.mark"):
            for _ in range(20):
                cc.is_correction("그게 아니라 이렇게 해")
        self.assertEqual(len(spawned), 1)


SYN = "SYNTH" + "abc123xyz"            # built at run time: never a literal credential-shaped string
SYN_LOWER = "hunter" + "2pass"


class AllowlistRound4(unittest.TestCase):
    def san(self, **ti):
        return observe_meta.sanitize({"tool_input": ti})["tool_input"]

    def test_1a_1b_1c_values_hidden_in_flags_and_program_names(self):
        for cmd in (f"mysql -p{SYN} db", f"./{SYN} --run", f"tool-ghp_{SYN}x go", "app --sk-live-q1w2e3r4 go"):
            out = self.san(command=cmd)["command"].lower()
            self.assertNotIn(SYN.lower(), out, cmd)
            self.assertNotIn("q1w2e3r4", out, cmd)
        self.assertEqual(self.san(command=f"mysql -p{SYN} db")["command"], "mysql -p db")

    def test_1e_useful_shape_kept(self):
        self.assertEqual(self.san(command="aws s3 ls")["command"], "aws s3 ls")
        self.assertEqual(self.san(command="npm run build:prod")["command"], "npm run build:prod")
        self.assertEqual(self.san(command="kubectl get pods -n prod-1")["command"], "kubectl get pods -n")

    def test_2a_url_keeps_scheme_and_host_only(self):
        self.assertEqual(self.san(url=f"https://api.example.com/v1/x?sig={SYN}&k=abc")["url"], "https://api.example.com")

    def test_2b_2c_free_text_fields_keep_words_not_values(self):
        d = self.san(description=f"Run tests; password is {SYN} AKIA{SYN}", pattern=f"{SYN_LOWER}|token={SYN}")
        self.assertNotIn(SYN.lower(), json.dumps(d).lower())
        self.assertNotIn(SYN_LOWER, json.dumps(d))
        self.assertIn("run tests", d["description"].lower())


class CorrectionSecrets(unittest.TestCase):
    def test_2d_secrets_in_a_correction_are_masked(self):
        key = "sk_" + "live_" + "q1w2e3r4" * 3
        rec = cc.make_record("s", "/x", f"그게 아니라 이 키 {key} 말고 https://u:{SYN}@h/x 써 AKIA{'Z9Y8X7W6V5U4T3S2'}")
        self.assertNotIn(key, rec["text"])
        self.assertNotIn(SYN, rec["text"])
        self.assertNotIn("Z9Y8X7W6V5U4T3S2", rec["text"])
        self.assertIn("그게 아니라", rec["text"])


class SpawnMarkRound4(unittest.TestCase):
    def setUp(self):
        self.mark = Path(tempfile.mkdtemp()) / "mark"
        cc._spawned_here = False  # per-process fallback flag; earlier tests in this process may have set it

    def spawn_count(self, n=10):
        spawned = []
        with mock.patch.object(cc, "_tokens_from_server", side_effect=OSError("down")), \
             mock.patch.object(cc.pc, "start_detached", lambda argv, task: spawned.append(1)), \
             mock.patch.object(cc, "SPAWN_MARK", self.mark):
            for _ in range(n):
                cc.is_correction("그게 아니라 이렇게 해")
        return len(spawned)

    def test_3b_future_mtime_does_not_block_forever(self):
        self.mark.touch()
        future = __import__("time").time() + 3600
        os.utime(self.mark, (future, future))
        self.assertEqual(self.spawn_count(), 1)

    def test_3c_unwritable_mark_still_spawns_once(self):
        with mock.patch.object(Path, "touch", side_effect=OSError("read-only")), \
             mock.patch.object(os, "open", side_effect=OSError("read-only")):
            self.assertEqual(self.spawn_count(), 1)

    def test_3a_concurrent_processes_spawn_once_per_window(self):
        import subprocess
        code = (f"import sys;sys.path.insert(0,{str(_ECC)!r});import capture_correction as cc;from pathlib import Path;"
                f"cc.SPAWN_MARK=Path({str(self.mark)!r});cc._tokens_from_server=lambda *a,**k:(_ for _ in ()).throw(OSError());"
                f"import platform_compat as pc;pc.start_detached=lambda a,t:print('SPAWN',flush=True);cc.is_correction('그게 아니라 x')")
        procs = [subprocess.Popen([sys.executable, "-I", "-c", code], stdout=subprocess.PIPE, text=True) for _ in range(20)]
        outs = "".join(p.communicate(timeout=60)[0] for p in procs)
        self.assertEqual(outs.count("SPAWN"), 1)


if __name__ == "__main__":
    unittest.main()
