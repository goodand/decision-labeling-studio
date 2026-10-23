"""Repositories the user handed over in prompts, listed once each for reuse.

Reads the same human prompts backfill reads (its readers and filters, nothing new) and collects
github.com URLs. One repo appears in many forms (case, .git, ?utm_source, /tree/…, /blob/…); all
collapse to one lowercase owner/repo key, with sub-paths kept. Forks group under their parent using
GitHub metadata (gh api), so duplicates across forks show as one entry.

Usage: python repo_refs.py [--no-meta] [--out DIR]   (default DIR: the ecc-clv2 store)
Writes referenced_repos.json (machine) and referenced_repos.md (for reading).
"""
import argparse, json, re, subprocess, sys
from collections import namedtuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import platform_compat as pc  # noqa: E402

Ref = namedtuple("Ref", "key display subpath")
_URL = re.compile(r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9][\w.-]*)/([A-Za-z0-9][\w.-]*)((?:/[^\s?#)\]>\"'`,;]*)?)", re.I)
# github.com/<first segment> that is a site page, not an owner
_NOT_OWNER = {"settings", "orgs", "topics", "search", "marketplace", "features", "explore", "notifications",
              "pulls", "issues", "login", "sponsors", "apps", "about", "pricing", "collections", "trending", "users"}


def extract(text: str) -> list:
    out = []
    for m in _URL.finditer(text):
        start = m.start()
        if start > 0 and text[start - 1] in "./" and not text[max(0, start - 8):start].lower().endswith(("://", "www.")):
            continue  # gist.github.com, api.github.com, raw.githubusercontent…
        owner, repo, rest = m.group(1), m.group(2), m.group(3) or ""
        if owner.lower() in _NOT_OWNER:
            continue
        repo = re.sub(r"\.git$", "", repo).rstrip(".")
        rest = rest.strip("/").rstrip(".")
        sub = rest if rest.split("/", 1)[0] in ("tree", "blob", "commit", "pull", "issues", "releases", "wiki") else ""
        out.append(Ref(f"{owner}/{repo}".lower(), f"{owner}/{repo}", sub))
    return out


class Catalog:
    def __init__(self):
        self.repos = {}  # key -> dict

    def add(self, session: str, when: str, text: str):
        day = (when or "")[:10]
        for r in extract(text):
            e = self.repos.setdefault(r.key, {"repo": r.display, "sessions": set(), "mentions": 0,
                                              "first_seen": day, "last_seen": day, "subpaths": set()})
            e["sessions"].add(session)
            e["mentions"] += 1
            if day:
                e["first_seen"] = min(filter(None, [e["first_seen"], day]))
                e["last_seen"] = max(e["last_seen"], day)
            if r.subpath:
                e["subpaths"].add(r.subpath)

    def entries(self) -> list:
        rows = [{**e, "sessions": len(e["sessions"]), "subpaths": sorted(e["subpaths"])} for e in self.repos.values()]
        return sorted(rows, key=lambda r: (-r["sessions"], r["repo"].lower()))

    def groups(self, meta_of) -> list:
        """meta_of(key) -> {"fork": bool, "parent": "owner/repo"|None, ...} or None (unreachable)."""
        meta = {k: meta_of(k) for k in self.repos}
        root = {}
        for k, m in meta.items():
            p = (m or {}).get("parent") if (m or {}).get("fork") else None
            root[k] = p.lower() if p else k
        out = {}
        for k, e in self.repos.items():
            g = out.setdefault(root[k], {"canonical": None, "variants": [], "sessions": set(), "mentions": 0,
                                         "first_seen": e["first_seen"], "last_seen": e["last_seen"], "subpaths": set()})
            g["variants"].append(e["repo"])
            g["sessions"] |= e["sessions"]
            g["mentions"] += e["mentions"]
            g["first_seen"] = min(filter(None, [g["first_seen"], e["first_seen"]]), default="")
            g["last_seen"] = max(g["last_seen"], e["last_seen"])
            g["subpaths"] |= e["subpaths"]
            if k == root[k] or g["canonical"] is None:
                g["canonical"] = e["repo"] if k == root[k] else (meta[k] or {}).get("parent") or e["repo"]
        rows = []
        for r, g in out.items():
            canon_meta = meta.get(r) if r in meta else meta_of(r)
            rows.append({**g, "sessions": len(g["sessions"]), "subpaths": sorted(g["subpaths"]),
                         "variants": sorted(set(g["variants"])), "meta": canon_meta})
        return sorted(rows, key=lambda r: (-r["sessions"], r["canonical"].lower()))


# Theme by fixed keywords on name + description (first match wins; empty when none). Groups repos that
# solve the same problem so near-duplicates sit together; identity duplicates are handled by groups().
THEMES = [("LLM wiki", ("llm-wiki", "llm_wiki", "wiki")), ("agent memory", ("memory", "mem0", "memos", "langmem", "letta", "graphiti", "cognee")),
          ("Lean / formal", ("lean", "theorem", "formal")), ("MCP server", ("mcp",)), ("skills / agents", ("skill", "agent")),
          ("NLP dataset / eval", ("folio", "amr", "ambigu", "inferential", "disjunction"))]


def theme(name: str, description: str) -> str:
    text = f"{name} {description or ''}".lower()
    return next((t for t, kws in THEMES if any(k in text for k in kws)), "")


def gh_meta(key: str):
    try:
        r = subprocess.run(["gh", "api", f"repos/{key}", "-q",
                            "{fork, parent: .parent.full_name, full_name, description, stars: .stargazers_count,"
                            " license: .license.spdx_id, archived, pushed: .pushed_at, private, language}"],
                           capture_output=True, text=True, timeout=20)
        return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None
    except (subprocess.SubprocessError, OSError, ValueError):
        return None


def to_markdown(rows) -> str:
    lines = ["# 프롬프트로 건넨 GitHub 저장소", "",
             f"중복 제거 후 {len(rows)}개 (URL 변형·fork를 하나로 묶음). 세션 수 = 서로 다른 대화에서 건넨 횟수.", "",
             "| 주제 | 세션 | 저장소 | 설명 | ★ | 라이선스 | 최근 push | 묶인 변형 · 하위 경로 |", "|---|---:|---|---|---:|---|---|---|"]
    for r in rows:
        r["theme"] = theme(r["canonical"], (r["meta"] or {}).get("description"))
    rows = sorted(rows, key=lambda r: (r["theme"] == "", r["theme"], -r["sessions"], r["canonical"].lower()))
    for r in rows:
        m = r["meta"] or {}
        state = "접근 불가" if r["meta"] is None else ("보관됨" if m.get("archived") else (m.get("pushed") or "")[:10])
        extra = ", ".join(v for v in r["variants"] if v.lower() != r["canonical"].lower())
        sub = ", ".join(r["subpaths"][:3]) + (" …" if len(r["subpaths"]) > 3 else "")
        desc = (m.get("description") or "").replace("|", "/")[:70]
        lines.append(f"| {r['theme'] or '기타'} | {r['sessions']} | [{r['canonical']}](https://github.com/{r['canonical']}) | {desc} | "
                     f"{m.get('stars', '')} | {m.get('license') or ''} | {state} | {'; '.join(filter(None, [extra, sub]))} |")
    return "\n".join(lines) + "\n"


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-meta", action="store_true", help="skip GitHub metadata (no network)")
    ap.add_argument("--out", default="", help="output directory (default: the store)")
    a = ap.parse_args(argv)
    import backfill as b  # reuse readers and the human-prompt filter
    cat = Catalog()
    files = sorted(b.CLAUDE_ROOT.glob("*/*.jsonl")) + sorted(b.CODEX_ROOT.rglob("rollout-*.jsonl"))
    for f in files:
        rd = b.read_codex if f.name.startswith("rollout-") else b.read_claude
        for it in rd(f):
            if it[0] == "prompt" and b.is_human_prompt(it[4]):
                cat.add(it[2], it[1], it[4])
    rows = cat.groups((lambda k: {"fork": False, "parent": None}) if a.no_meta else gh_meta)
    out = Path(a.out).expanduser() if a.out else pc.store_dir()
    out.mkdir(parents=True, exist_ok=True)
    (out / "referenced_repos.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), "utf-8")
    (out / "referenced_repos.md").write_text(to_markdown(rows), "utf-8")
    print(f"{len(cat.repos)} distinct repo keys -> {len(rows)} groups; written to {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
