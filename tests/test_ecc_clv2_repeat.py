"""Repeated-instruction detector: a phrase the user writes in several DIFFERENT sessions is a standing
instruction the agent has not learned yet. Pure string rules (no Kiwi): NFKC, lowercase, trailing-josa
strip from a fixed list, word n-grams, distinct-session counts. Fixtures are synthetic."""
import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

_ECC = Path(__file__).resolve().parents[1] / "tools" / "ecc-clv2"
if not (os.environ.get("ECC_CLV2_SKILL_DIR") or (_ECC / "upstream" / "continuous-learning-v2").exists()):
    raise unittest.SkipTest("ECC continuous-learning-v2 upstream copy missing (set ECC_CLV2_SKILL_DIR)")
sys.path.insert(0, str(_ECC))
import repeat_instr as ri  # noqa: E402


class Normalize(unittest.TestCase):
    def test_trailing_josa_and_case_and_width(self):
        self.assertEqual(ri.words("장단점을 설명하고 ＴＤＤ로 해"), ["장단점", "설명하고", "tdd", "해"])

    def test_josa_not_stripped_below_two_chars(self):
        self.assertEqual(ri.words("이를 봐"), ["이를", "봐"])  # stripping would leave 1 char


class Noise(unittest.TestCase):
    """Real-prompt run 2026-10-24: top 'instructions' were path fragments, URLs and light verbs
    ('users jaehyuntak desktop', 'https github com', '할 수'). Those are masked or need a content word."""
    def test_paths_and_urls_are_masked_before_indexing(self):
        self.assertEqual(ri.words("cwd는 /Users/me/Desktop/x 봐 https://github.com/a/b 열어"),
                         ["cwd", "[경로]", "봐", "[url]", "열어"])

    def test_phrase_of_only_function_words_is_not_an_instruction(self):
        idx = ri.Index()
        for s in ("a", "b", "c"):
            idx.add(s, "할 수 있는 것 같은데")
        self.assertEqual(idx.repeated(min_sessions=3), [])

    def test_single_content_word_across_sessions_counts(self):
        idx = ri.Index()
        idx.add("a", "장단점을 꼭 적어")
        idx.add("b", "선택지마다 장단점 비교")
        idx.add("c", "장단점 설명 붙여줘")
        self.assertEqual(idx.repeated(min_sessions=3)[0], {"phrase": "장단점", "sessions": 3})


class Detect(unittest.TestCase):
    def test_phrase_in_three_sessions_is_an_instruction(self):
        idx = ri.Index()
        idx.add("s1", "상위개념 장단점 설명 객관식 질문으로 해줘")
        idx.add("s2", "늘 상위개념 장단점 설명 붙여")
        idx.add("s3", "이번에도 상위개념 장단점 설명 부탁")
        top = idx.repeated(min_sessions=3)
        self.assertEqual(top[0]["phrase"], "상위개념 장단점 설명")
        self.assertEqual(top[0]["sessions"], 3)

    def test_repeats_inside_one_session_do_not_count(self):
        idx = ri.Index()
        for _ in range(5):
            idx.add("s1", "검증 비용 줄여")
        self.assertEqual(idx.repeated(min_sessions=2), [])

    def test_shorter_phrase_with_same_sessions_is_subsumed(self):
        idx = ri.Index()
        for s in ("a", "b", "c"):
            idx.add(s, "검증 비용 줄여라")
        phrases = [r["phrase"] for r in idx.repeated(min_sessions=3)]
        self.assertIn("검증 비용 줄여라", phrases)
        self.assertNotIn("검증 비용", phrases)          # same 3 sessions as the longer phrase
        self.assertNotIn("비용 줄여라", phrases)

    def test_shorter_phrase_kept_when_it_has_more_sessions(self):
        idx = ri.Index()
        for s in ("a", "b", "c"):
            idx.add(s, "검증 비용 줄여라")
        idx.add("d", "검증 비용 계산")
        phrases = {r["phrase"]: r["sessions"] for r in idx.repeated(min_sessions=3)}
        self.assertEqual(phrases.get("검증 비용"), 4)

    def test_index_round_trips_and_merges(self):
        a, b = ri.Index(), ri.Index()
        a.add("s1", "line by line patch")
        b.add("s2", "line by line patch")
        b.add("s3", "line by line patch")
        a.merge(ri.Index.from_json(b.to_json()))
        self.assertEqual(a.repeated(min_sessions=3)[0]["phrase"], "line by line patch")

    def test_record_shape_is_metadata_safe(self):
        idx = ri.Index()
        for s in ("a", "b", "c"):
            idx.add(s, "장단점 설명 D:/x/예산서.hwpx")
        rec = ri.records(idx, min_sessions=3)[0]
        self.assertEqual(rec["event"], "user_repeated_instruction")
        self.assertEqual(rec["sessions"], 3)
        self.assertNotIn(".hwpx", json.dumps(rec, ensure_ascii=False))


class Backfill(unittest.TestCase):
    def test_backfill_writes_derived_file_and_is_idempotent(self):
        import backfill
        tmp = Path(tempfile.mkdtemp())
        backfill.STORE = tmp / "store"
        src = tmp / "src"
        src.mkdir()
        for i in range(3):
            line = {"type": "user", "sessionId": f"sess-{i}", "timestamp": "2026-10-20T00:00:00Z", "cwd": "/none",
                    "isSidechain": False, "entrypoint": "cli", "message": {"role": "user", "content": "상위개념 장단점 설명 해줘"}}
            (src / f"s{i}.jsonl").write_text(json.dumps(line, ensure_ascii=False) + "\n", "utf-8")
        for _ in range(2):  # second run: files unchanged -> skipped by state, derived file must not change
            run = backfill.Run(False, "", True)
            for f in sorted(src.glob("*.jsonl")):
                run.process(f, backfill.read_claude)
            run.flush()
        out = [json.loads(l) for l in (backfill.STORE / "repeated_instructions.jsonl").read_text("utf-8").splitlines()]
        self.assertEqual([(r["phrase"], r["sessions"]) for r in out], [("상위개념 장단점 설명 해줘", 3)])


class LearnNow(unittest.TestCase):
    def test_repeated_instructions_reach_the_learner(self):
        import learn_now
        store = Path(tempfile.mkdtemp())
        pdir = store / "projects" / "p"
        pdir.mkdir(parents=True)
        obs = {"timestamp": "t", "event": "tool_start", "tool": "Bash", "session": "s", "input": "{}"}
        (pdir / "observations.jsonl").write_text("\n".join([json.dumps(obs)] * 25), "utf-8")
        rep = {"event": "user_repeated_instruction", "phrase": "장단점 설명", "sessions": 4, "text": "장단점 설명"}
        (store / "repeated_instructions.jsonl").write_text(json.dumps(rep, ensure_ascii=False) + "\n", "utf-8")
        seen = {}

        def fake_run(cmd, cwd, input, **kw):
            name = next((cwd / ".observer-tmp").glob("analysis-*.jsonl"))
            seen["analysis"] = name.read_text("utf-8")
            seen["prompt"] = input.decode("utf-8")
            return mock.Mock(stdout=b'{"status":"analysis_complete"}', stderr=b"", returncode=0)

        with mock.patch.object(learn_now, "STORE", store), mock.patch.object(learn_now.subprocess, "run", fake_run):
            learn_now.run(pdir, {"id": "p", "name": "n"})
        self.assertIn("user_repeated_instruction", seen["analysis"])
        self.assertIn("user_repeated_instruction", seen["prompt"])

    def test_repeated_lines_cannot_crowd_out_observations_and_corrections(self):
        """learn_now keeps the last MAX_LINES lines; 1,588 repeated phrases (real run) would push out every
        observation and correction. Repeated instructions get their own budget, highest sessions first."""
        import learn_now
        store = Path(tempfile.mkdtemp())
        pdir = store / "projects" / "p"
        pdir.mkdir(parents=True)
        obs = {"timestamp": "t", "event": "tool_start", "tool": "Bash", "session": "s", "input": "{}"}
        corr = {"timestamp": "t", "event": "user_correction", "session": "s", "text": "그게 아니라"}
        (pdir / "observations.jsonl").write_text("\n".join([json.dumps(obs)] * 300), "utf-8")
        (pdir / "corrections.jsonl").write_text(json.dumps(corr, ensure_ascii=False), "utf-8")
        reps = [{"event": "user_repeated_instruction", "phrase": f"p{i}", "sessions": 3 + i % 7, "text": f"p{i}"}
                for i in range(1600)]
        (store / "repeated_instructions.jsonl").write_text("\n".join(json.dumps(r) for r in reps), "utf-8")
        seen = {}

        def fake_run(cmd, cwd, input, **kw):
            seen["lines"] = [json.loads(l) for l in next((cwd / ".observer-tmp").glob("analysis-*.jsonl")).read_text("utf-8").splitlines() if l]
            return mock.Mock(stdout=b'{"status":"analysis_complete"}', stderr=b"", returncode=0)

        with mock.patch.object(learn_now, "STORE", store), mock.patch.object(learn_now.subprocess, "run", fake_run):
            learn_now.run(pdir, {"id": "p", "name": "n"})
        ev = [l["event"] for l in seen["lines"]]
        self.assertIn("user_correction", ev)
        self.assertGreaterEqual(ev.count("tool_start"), 300)
        rep = [l for l in seen["lines"] if l["event"] == "user_repeated_instruction"]
        self.assertEqual(len(rep), learn_now.MAX_REPEATED)
        self.assertEqual(min(r["sessions"] for r in rep), max(r["sessions"] for r in reps) - 0)  # top by sessions


if __name__ == "__main__":
    unittest.main()
