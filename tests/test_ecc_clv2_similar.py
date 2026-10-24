"""BM25 similar-instruction search (STUDIO-ECC-023): find the same instruction said in OTHER sessions even when
the wording differs. Deterministic: pinned Kiwi tokens + human-approved synonyms + BM25. Unit tests inject a
whitespace tokenizer; the Kiwi path is covered by the real-run check."""
import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

_ECC = Path(__file__).resolve().parents[1] / "tools" / "ecc-clv2"
if not (os.environ.get("ECC_CLV2_SKILL_DIR") or (_ECC / "upstream" / "continuous-learning-v2").exists()):
    raise unittest.SkipTest("ECC continuous-learning-v2 upstream copy missing (set ECC_CLV2_SKILL_DIR)")
sys.path.insert(0, str(_ECC))
import similar, synonyms  # noqa: E402

TOK = lambda t: t.lower().split()  # noqa: E731
DOCS = [("s1", "2026-08-30", "test code 작성 후 적대적 검증 돌린다"),
        ("s2", "2026-09-01", "의존성 분석 결정론적인 것 순서"),
        ("s3", "2026-09-05", "폐쇄형 질문 해라 선택지"),
        ("s4", "2026-09-06", "오늘 날씨 질문")]


class Search(unittest.TestCase):
    def test_rare_shared_terms_rank_first_and_order_is_deterministic(self):
        idx = similar.Index(DOCS, tokenize=TOK, synonyms=synonyms.EMPTY)
        hits = idx.search("test code 도 적대적 검증 하고 있어", k=2)
        self.assertEqual(hits[0][1:3], ("s1", "2026-08-30"))
        self.assertEqual(hits, idx.search("test code 도 적대적 검증 하고 있어", k=2))

    def test_same_session_is_excluded(self):
        idx = similar.Index(DOCS, tokenize=TOK, synonyms=synonyms.EMPTY)
        self.assertFalse([h for h in idx.search("의존성 분석 순서", exclude_session="s2") if h[1] == "s2"])

    def test_approved_synonyms_bridge_different_words(self):
        syn = synonyms.load(synonyms.DEFAULT_PATH)                  # SYN-001 {객관식, 폐쇄형}
        idx = similar.Index(DOCS, tokenize=TOK, synonyms=syn)
        self.assertEqual(idx.search("객관식 질문 해라", k=1)[0][1], "s3")
        idx_off = similar.Index(DOCS, tokenize=TOK, synonyms=synonyms.EMPTY)
        self.assertGreater(idx.search("객관식 질문 해라", k=1)[0][0], idx_off.search("객관식 질문 해라", k=1)[0][0])


class Pairs(unittest.TestCase):
    def test_cross_session_pairs_above_threshold_masked_and_capped(self):
        docs = DOCS + [("s9", "2026-10-24", "Test Code 작성 후 적대적 검증 돌린다 sk_" + "live_" + "q1w2e3r4" * 3 + " " + "x" * 400)]
        recs = similar.pairs(docs, tokenize=TOK, synonyms=synonyms.EMPTY, min_score=0.1)
        r = next(r for r in recs if r["session"] == "s9")
        self.assertEqual((r["event"], r["match_session"], r["match_date"]), ("user_similar_instruction", "s1", "2026-08-30"))
        self.assertNotIn("q1w2e3r4", json.dumps(recs))
        self.assertLessEqual(len(r["text"]), 300)
        self.assertTrue(all(r["session"] != r["match_session"] for r in recs))

    def test_below_threshold_is_dropped(self):
        self.assertEqual(similar.pairs(DOCS, tokenize=TOK, synonyms=synonyms.EMPTY, min_score=1e9), [])


class Wiring(unittest.TestCase):
    def test_learn_now_gives_similar_lines_their_own_budget(self):
        import learn_now
        store = Path(tempfile.mkdtemp())
        pdir = store / "projects" / "p"
        pdir.mkdir(parents=True)
        obs = {"timestamp": "t", "event": "tool_start", "tool": "Bash", "session": "s", "input": "{}"}
        (pdir / "observations.jsonl").write_text("\n".join([json.dumps(obs)] * 300), "utf-8")
        sims = [{"event": "user_similar_instruction", "text": f"t{i}", "match_text": "m", "score": float(i)} for i in range(500)]
        (store / "similar_instructions.jsonl").write_text("\n".join(json.dumps(r) for r in sims), "utf-8")
        seen = {}

        def fake_run(cmd, cwd, input, **kw):
            seen["lines"] = [json.loads(l) for l in next((cwd / ".observer-tmp").glob("analysis-*.jsonl")).read_text("utf-8").splitlines() if l]
            seen["prompt"] = input.decode("utf-8")
            return mock.Mock(stdout=b'{"status":"analysis_complete"}', stderr=b"", returncode=0)

        with mock.patch.object(learn_now, "STORE", store), mock.patch.object(learn_now.subprocess, "run", fake_run):
            learn_now.run(pdir, {"id": "p", "name": "n"})
        got = [l for l in seen["lines"] if l["event"] == "user_similar_instruction"]
        self.assertEqual(len(got), learn_now.MAX_SIMILAR)
        self.assertEqual(min(l["score"] for l in got), 500 - learn_now.MAX_SIMILAR)   # top by score
        self.assertGreaterEqual(sum(l["event"] == "tool_start" for l in seen["lines"]), 300)
        self.assertIn("user_similar_instruction", seen["prompt"])



class BackfillWiring(unittest.TestCase):
    def test_backfill_writes_cross_session_pairs_and_is_idempotent(self):
        import backfill
        tmp = Path(tempfile.mkdtemp())
        backfill.STORE = tmp / "store"
        src = tmp / "src"
        src.mkdir()
        for i, (sess, text) in enumerate([("a1", "test code 작성 후 적대적 검증 돌린다"), ("b2", "test code 도 적대적 검증 하고 있어"),
                                          ("c3", "오늘 날씨 어때")]):
            line = {"type": "user", "sessionId": sess, "timestamp": f"2026-10-2{i}T00:00:00Z", "cwd": "/none",
                    "isSidechain": False, "entrypoint": "cli", "message": {"role": "user", "content": text}}
            (src / f"{sess}.jsonl").write_text(json.dumps(line, ensure_ascii=False) + "\n", "utf-8")
        for _ in range(2):
            run = backfill.Run(False, "", True)
            run.similar_tokenize, run.similar_min_score = TOK, 0.1
            for f in sorted(src.glob("*.jsonl")):
                run.process(f, backfill.read_claude)
            run.flush()
        out = [json.loads(l) for l in (backfill.STORE / "similar_instructions.jsonl").read_text("utf-8").splitlines()]
        self.assertEqual(sorted((r["session"], r["match_session"]) for r in out), [("a1", "b2"), ("b2", "a1")])
        self.assertEqual(run.files["similar_instructions"], 2)

    def test_regex_mode_skips_instead_of_switching_tokenizer(self):
        import backfill
        tmp = Path(tempfile.mkdtemp())
        backfill.STORE = tmp / "store"
        run = backfill.Run(False, "", True)
        run.similar_tokenize = None   # what main() sets when the detector is regex (no pinned Kiwi)
        run.flush()
        self.assertFalse((backfill.STORE / "similar_instructions.jsonl").exists())
        self.assertEqual(run.files["similar_instructions"], "skipped (no pinned Kiwi)")



class LiveSessionIndexes(unittest.TestCase):
    def test_live_session_prompts_feed_indexes_but_write_no_records(self):
        """Found on the first real run: the live guard skipped the whole session, so its prompts never reached the
        BM25 corpus or the repeat index. Indexes are keyed by origin (no duplicates); only records are guarded."""
        import backfill
        tmp = Path(tempfile.mkdtemp())
        backfill.STORE = tmp / "store"
        backfill.STORE.mkdir(parents=True)
        (backfill.STORE / "observations.jsonl").write_text(json.dumps({"session": "live1", "event": "tool_start"}) + "\n", "utf-8")
        src = tmp / "src"
        src.mkdir()
        for sess, text in [("live1", "그게 아니라 test code 작성 후 적대적 검증"), ("old2", "test code 작성 후 적대적 검증 돌린다")]:
            line = {"type": "user", "sessionId": sess, "timestamp": "2026-10-20T00:00:00Z", "cwd": "/none",
                    "isSidechain": False, "entrypoint": "cli", "message": {"role": "user", "content": text}}
            (src / f"{sess}.jsonl").write_text(json.dumps(line, ensure_ascii=False) + "\n", "utf-8")
        run = backfill.Run(False, "", True)
        run.similar_tokenize, run.similar_min_score = TOK, 0.1
        for f in sorted(src.glob("*.jsonl")):
            run.process(f, backfill.read_claude)
        run.flush()
        sims = [json.loads(l) for l in (backfill.STORE / "similar_instructions.jsonl").read_text("utf-8").splitlines()]
        self.assertIn(("live1", "old2"), {(r["session"], r["match_session"]) for r in sims})
        corr = backfill.STORE / "corrections.jsonl"
        self.assertFalse(corr.exists() and "live1" in corr.read_text("utf-8"))   # no record replayed for the live session



class DerivedRecordsAreNotLive(unittest.TestCase):
    def test_similar_and_repeat_records_never_mark_a_session_live(self):
        """First real run: similar_instructions.jsonl rows carry "session", so 20 past sessions looked live and
        would have stopped receiving records. Only what the live hooks write counts as live."""
        import backfill
        tmp = Path(tempfile.mkdtemp())
        backfill.STORE = tmp / "store"
        backfill.STORE.mkdir(parents=True)
        (backfill.STORE / "similar_instructions.jsonl").write_text(
            json.dumps({"event": "user_similar_instruction", "session": "old1", "match_session": "old2"}) + "\n", "utf-8")
        (backfill.STORE / "observations.jsonl").write_text(json.dumps({"event": "tool_start", "session": "live9"}) + "\n", "utf-8")
        self.assertEqual(backfill.live_sessions(), {"live9"})



class Threshold(unittest.TestCase):
    """MIN_SCORE is set from a labeled sample (tests/fixtures/similar_labels.json, STUDIO-ECC-024): the lowest
    band edge at which the cumulative precision for same_instruction of everything above it reaches TARGET."""
    def test_min_score_matches_the_labeled_fixture(self):
        fx = json.loads((Path(__file__).resolve().parent / "fixtures" / "similar_labels.json").read_text("utf-8"))
        if fx.get("positive") is None:
            self.skipTest("which labels count as positive is undecided (STUDIO-ECC-024)")
        self.assertEqual(fx["chosen"], similar.choose_threshold(fx["items"], fx["target_precision"], positive=tuple(fx["positive"])))
        self.assertEqual(similar.MIN_SCORE, fx["chosen"])

    def test_choose_threshold_rule(self):
        items = [{"score": 11, "label": "unrelated"}, {"score": 12, "label": "same_instruction"},
                 {"score": 17, "label": "same_topic"}, {"score": 17.5, "label": "same_instruction"},
                 {"score": 19, "label": "same_instruction"}, {"score": 21, "label": "same_instruction"},
                 {"score": 26, "label": "unrelated"}, {"score": 27, "label": "same_instruction"}, {"score": 31, "label": "same_instruction"}]
        bands = [(10, 13), (13, 16), (16, 18), (18, 20), (20, 25), (25, 30), (30, 999)]
        # cumulative precision at each edge: >=30 1.0 | >=25 .67 | >=20 .75 | >=18 .80 | >=16 .71 | >=10 .67
        self.assertEqual(similar.choose_threshold(items, 0.8, bands=bands), 18)   # lowest edge whose cumulative set meets 0.8
        self.assertEqual(similar.choose_threshold(items, 0.5, bands=bands), 10)
        self.assertEqual(similar.choose_threshold(items, 1.1, bands=bands), None)


if __name__ == "__main__":
    unittest.main()
