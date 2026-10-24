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


if __name__ == "__main__":
    unittest.main()
