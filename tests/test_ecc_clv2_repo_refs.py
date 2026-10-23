"""Repositories the user handed over in prompts, listed once each for reuse. Many URL variants of
one repo (case, .git, ?utm, /tree/..., /blob/...) must collapse to one entry; forks group under their
parent. Fixtures are synthetic; GitHub metadata is injected, not fetched."""
import json, os, sys, tempfile, unittest
from pathlib import Path

_ECC = Path(__file__).resolve().parents[1] / "tools" / "ecc-clv2"
if not (os.environ.get("ECC_CLV2_SKILL_DIR") or (_ECC / "upstream" / "continuous-learning-v2").exists()):
    raise unittest.SkipTest("ECC continuous-learning-v2 upstream copy missing (set ECC_CLV2_SKILL_DIR)")
sys.path.insert(0, str(_ECC))
import repo_refs as rr  # noqa: E402


class Extract(unittest.TestCase):
    def test_variants_collapse_to_one_key_and_keep_subpaths(self):
        text = ("봐 https://github.com/Yale-LILY/FOLIO?utm_source=chatgpt.com 그리고 github.com/yale-lily/folio.git "
                "또 https://github.com/Yale-LILY/FOLIO/blob/main/LICENSE 와 www.github.com/Yale-LILY/FOLIO/tree/main/data).")
        refs = rr.extract(text)
        self.assertEqual({r.key for r in refs}, {"yale-lily/folio"})
        self.assertEqual({r.subpath for r in refs} - {""}, {"blob/main/LICENSE", "tree/main/data"})
        self.assertEqual(refs[0].display, "Yale-LILY/FOLIO")

    def test_non_repo_github_urls_are_ignored(self):
        text = "https://github.com/settings/tokens https://github.com/orgs/x/people https://gist.github.com/a/b github.com/goodand"
        self.assertEqual(rr.extract(text), [])

    def test_trailing_punctuation_is_not_part_of_the_name(self):
        self.assertEqual([r.key for r in rr.extract("(https://github.com/oOo0oOo/lean-lsp-mcp), 참고")], ["ooo0ooo/lean-lsp-mcp"])


class Collect(unittest.TestCase):
    def test_distinct_sessions_first_and_last_seen(self):
        c = rr.Catalog()
        c.add("s1", "2026-08-01T00:00:00Z", "github.com/goodand/vault")
        c.add("s1", "2026-08-02T00:00:00Z", "https://github.com/goodand/vault.git")
        c.add("s2", "2026-09-01T00:00:00Z", "https://github.com/goodand/vault/tree/main")
        (e,) = c.entries()
        self.assertEqual((e["repo"], e["sessions"], e["mentions"]), ("goodand/vault", 2, 3))
        self.assertEqual((e["first_seen"], e["last_seen"]), ("2026-08-01", "2026-09-01"))

    def test_forks_group_under_parent(self):
        c = rr.Catalog()
        c.add("s1", "2026-08-01T00:00:00Z", "github.com/goodand/perfect-structure")
        c.add("s2", "2026-08-03T00:00:00Z", "github.com/f-mac-mows/perfect-structure/tree/main/test")
        meta = {"goodand/perfect-structure": {"fork": True, "parent": "f-mac-mows/perfect-structure", "stars": 0},
                "f-mac-mows/perfect-structure": {"fork": False, "parent": None, "stars": 3}}
        groups = c.groups(lambda key: meta.get(key))
        (g,) = groups
        self.assertEqual(g["canonical"], "f-mac-mows/perfect-structure")
        self.assertEqual(sorted(g["variants"]), ["f-mac-mows/perfect-structure", "goodand/perfect-structure"])
        self.assertEqual(g["sessions"], 2)

    def test_unreachable_repo_is_kept_and_marked(self):
        c = rr.Catalog()
        c.add("s1", "2026-08-01T00:00:00Z", "github.com/gone/away")
        (g,) = c.groups(lambda key: None)
        self.assertEqual((g["canonical"], g["meta"]), ("gone/away", None))



class Themes(unittest.TestCase):
    def test_theme_from_name_and_description_by_fixed_keywords(self):
        self.assertEqual(rr.theme("mem0ai/mem0", "The Memory Layer for AI Agents"), "agent memory")
        self.assertEqual(rr.theme("SamurAIGPT/llm-wiki-agent", "A personal knowledge base"), "LLM wiki")
        self.assertEqual(rr.theme("oOo0oOo/lean-lsp-mcp", "Lean Theorem Prover MCP"), "Lean / formal")
        self.assertEqual(rr.theme("cli/cli", "GitHub’s official command line tool"), "")


if __name__ == "__main__":
    unittest.main()
