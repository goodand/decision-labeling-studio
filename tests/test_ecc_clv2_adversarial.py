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
        self.assertTrue(s["command"].startswith("cat > a.py <<"))

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


if __name__ == "__main__":
    unittest.main()
