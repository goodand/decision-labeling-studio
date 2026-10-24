"""Replay past agent session logs through the ecc-clv2 capture rules (one-off, idempotent).

The live hooks only see sessions that run after they were installed. This reads the transcripts
Claude Code and Codex already wrote and produces the same two record kinds, with the same
filters, into the same store, so learn_now/auto_learn can run on them unchanged:
  corrections.jsonl   user prompts that capture_correction.is_correction accepts (<= 300 chars, doc paths masked)
  observations.jsonl  tool_start/tool_complete pairs with metadata-only input (observe_meta.sanitize), output ""
Nothing else from a transcript is kept: no assistant text, no tool output, no file contents.

Skipped on purpose: subagent transcripts (sidechain / thread_source=subagent), automated runs
(entrypoint sdk-cli, promptSource sdk, sessionKind bg, [ECC-AUTOMATED]), meta/compact-summary
lines, and injected prompts (text starting with "<": task notifications, command echoes, env context).

Sources:  ~/.claude/projects/<cwd-slug>/*.jsonl   (Claude Code; nested */subagents/ are skipped)
          ~/.codex/sessions/**/rollout-*.jsonl     (Codex)
          <repo>/decisions/**/*.json              (curated decision logs, via --decisions; bypass the detector)
Usage:    python backfill.py [--dry-run] [--since YYYY-MM-DD] [--source claude|codex] [--decisions DIR] [--project-root DIR] [--no-state] [path ...]
State:    <store>/backfill_state.json remembers lines done per file, so re-runs only add new lines.
"""
import argparse, hashlib, json, os, re, subprocess, sys, time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capture_correction as cc  # noqa: E402  (correction rule, record shape, automated marker)
import observe_meta  # noqa: E402  (metadata-only input filter)
import platform_compat as pc  # noqa: E402
import repeat_instr as ri  # noqa: E402  (cross-session repeated instructions)
import similar  # noqa: E402  (BM25 similar instructions across sessions, pinned Kiwi tokens)

STORE = pc.store_dir()
MAX_FILE_SIZE_MB = 10  # same rotation as observe.sh
CLAUDE_ROOT = Path.home() / ".claude" / "projects"
CODEX_ROOT = Path.home() / ".codex" / "sessions"
# observe.sh's secret scrub (defense in depth; metadata-only capture is the real boundary)
_SECRET_RE = re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization|credentials?|auth)"
                        r"""(["'\s:=\\]{1,8})((?:bearer|basic|token|bot)\s+)?([A-Za-z0-9_\-/.+=]{8,256})""")
# Codex tool names -> the Claude Code names ECC's patterns are written for
CODEX_TOOLS = {"exec": "Bash", "exec_command": "Bash", "write_stdin": "Bash", "run": "Bash", "apply_patch": "Edit",
               "view_image": "Read", "update_plan": "TaskUpdate", "spawn_agent": "Agent", "wait_agent": "Agent",
               "request_user_input": "AskUserQuestion", "request_user_input_async": "AskUserQuestion",
               "web_search_call": "WebSearch", "tool_search_call": "ToolSearch"}
CODEX_ARG_KEYS = {"cmd": "command", "command": "command", "path": "file_path", "file_path": "file_path"}


def scrub(s: str) -> str:
    return _SECRET_RE.sub(lambda m: m.group(1) + m.group(2) + (m.group(3) or "") + "[REDACTED]", s)


def ts(iso: str) -> str:
    """ISO 8601 (any offset) -> the UTC form observe.sh writes; falls back to now."""
    from datetime import datetime, timezone
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---- project identity (mirrors upstream scripts/detect-project.sh) --------------------------------
def normalize_remote(url: str) -> str:
    url = re.sub(r"://[^@]+@", "://", url)
    url = re.sub(r"^[A-Za-z][A-Za-z0-9+.-]*://", "", url)
    url = re.sub(r"^[^@/:]+@([^:/]+):", r"\1/", url)
    return re.sub(r"\.git/?$|/+$", "", url)


class Projects:
    """cwd -> (id, name, root, remote); 'global' when the cwd is gone or not in a git repo."""
    GLOBAL = ("global", "global", "", "")

    def __init__(self, force_root: str = ""):
        self.cache, self.seen = {}, {}
        self.forced = self.path_project(force_root) if force_root else None

    @staticmethod
    def path_project(root: str):
        """A non-git folder named explicitly, like detect-project.sh's CLAUDE_PROJECT_DIR 'env-nogit' case:
        identity is the hash of the resolved path."""
        root = os.path.realpath(os.path.expanduser(root))
        return (hashlib.sha256(root.encode("utf-8")).hexdigest()[:12], os.path.basename(root), root, "")

    def resolve(self, cwd: str):
        if self.forced:
            self.seen[self.forced[0]] = self.forced
            return self.forced
        if cwd in self.cache:
            return self.cache[cwd]
        meta = self.GLOBAL
        if cwd and os.path.isdir(cwd):
            try:
                root = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"], capture_output=True,
                                      text=True, timeout=10).stdout.strip()
                if root:
                    remote = subprocess.run(["git", "-C", root, "remote", "get-url", "origin"], capture_output=True,
                                            text=True, timeout=10).stdout.strip()
                    remote = re.sub(r"://[^@]+@", "://", remote)
                    key = normalize_remote(remote) if remote else root
                    pid = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
                    meta = (pid, os.path.basename(root), root, remote)
            except (subprocess.SubprocessError, OSError):
                pass
        self.cache[cwd] = meta
        self.seen[meta[0]] = meta
        return meta


# ---- readers: yield ("prompt", ts, session, cwd, text) | ("tool", ts, session, cwd, name, input_dict) ----
def read_claude(path: Path):
    if "/subagents/" in path.as_posix():
        return
    with path.open(encoding="utf-8", errors="replace") as fh:
        yield from _claude_lines(fh)


def _claude_lines(fh):
    for line in fh:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("isSidechain") or d.get("agentId"):
            continue
        human = (d.get("origin") or {}).get("kind") == "human"  # desktop app: promptSource "sdk" but origin human
        if d.get("entrypoint") == "sdk-cli" or d.get("sessionKind") == "bg" or (d.get("promptSource") == "sdk" and not human):
            continue
        if d.get("type") == "attachment":  # a message the human sent mid-turn (desktop app)
            a = d.get("attachment") or {}
            if (a.get("type") == "queued_command" and a.get("commandMode", "prompt") == "prompt"
                    and (a.get("humanTurn") or (a.get("origin") or {}).get("kind") == "human") and isinstance(a.get("prompt"), str)):
                yield ("prompt", a.get("timestamp") or d.get("timestamp", ""), d.get("sessionId", ""), d.get("cwd", ""), a["prompt"])
            continue
        if d.get("type") not in ("user", "assistant"):
            continue
        if d.get("isMeta") or d.get("isCompactSummary"):
            continue
        msg, when, sess, cwd = d.get("message") or {}, d.get("timestamp", ""), d.get("sessionId", ""), d.get("cwd", "")
        content = msg.get("content")
        if d["type"] == "assistant":
            for b in content if isinstance(content, list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    yield ("tool", when, sess, cwd, b.get("name", "unknown"), b.get("input") or {}, b.get("id", ""))
            continue
        if d.get("toolUseResult") is not None:
            continue
        if isinstance(content, list):
            if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                continue
            content = " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
        if isinstance(content, str):
            yield ("prompt", when, sess, cwd, _LEAD_REMINDER.sub("", content))


_LEAD_REMINDER = re.compile(r"^(?:\s*<system-reminder>.*?</system-reminder>)+\s*", re.S)  # harness text before the human's


def read_codex(path: Path):
    with path.open(encoding="utf-8", errors="replace") as fh:
        yield from _codex_lines(fh)


def _codex_lines(fh):
    sess, cwd = "", ""
    for line in fh:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        p, when = d.get("payload") or {}, d.get("timestamp", "")
        if d.get("type") == "session_meta":
            src = p.get("source")
            if p.get("thread_source") == "subagent" or (isinstance(src, dict) and "subagent" in src):
                return  # whole file is a subagent thread
            sess, cwd = p.get("id") or p.get("session_id", ""), p.get("cwd", "")
        elif d.get("type") == "turn_context":
            cwd = p.get("cwd", cwd)
        elif d.get("type") == "response_item":
            kind = p.get("type")
            if kind == "message" and p.get("role") == "user":
                text = " ".join(c.get("text", "") for c in p.get("content") or [] if isinstance(c, dict))
                yield ("prompt", when, sess, cwd, text)
            elif kind in ("function_call", "custom_tool_call", "web_search_call", "tool_search_call"):
                name = p.get("name", kind)
                args = p.get("arguments")
                try:
                    args = json.loads(args) if isinstance(args, str) else (args or {})
                except ValueError:
                    args = {}
                inp = {CODEX_ARG_KEYS[k]: v for k, v in args.items() if k in CODEX_ARG_KEYS} if isinstance(args, dict) else {}
                if kind == "custom_tool_call" and name == "exec" and isinstance(p.get("input"), str):
                    inp["command"] = p["input"]  # raw command line; apply_patch bodies are file content and stay out
                if isinstance(inp.get("command"), list):
                    inp["command"] = " ".join(map(str, inp["command"]))
                yield ("tool", when, sess, cwd, CODEX_TOOLS.get(name, f"codex:{name}"), inp, p.get("call_id", ""))


# Statuses that are NOT settled decisions; the learner would otherwise treat them as rules.
UNSETTLED = {"superseded", "explored_not_adopted", "under_consideration", "unresolved", "rejected", "proposed", "open"}


def read_decisions(path: Path):
    """Curated decision logs (decisions/**/*.json): already human-confirmed, so they bypass the
    correction detector. Accepts the studio shape {decisions:[{id,status,user_quote,decision}]} and
    the dds shape {decisions:[{id,status,decision,...}]}; other layouts yield nothing.
    Entries whose status is in UNSETTLED are counted but not yielded as decisions."""
    try:
        doc = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return
    items = doc.get("decisions") if isinstance(doc, dict) else None
    if not isinstance(items, list):
        return
    day = str(doc.get("recorded_on") or "")
    for e in items:
        if not isinstance(e, dict) or not e.get("decision"):
            continue
        when = str(e.get("recorded_on") or day)
        if str(e.get("status", "")).lower() in UNSETTLED:
            yield ("decision_unsettled", "", "", str(path.parent))
            continue
        yield ("decision", when + "T00:00:00Z" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", when) else "", f"decision:{path.stem}",
               str(path.parent), {"decision_id": str(e.get("id", "")), "status": str(e.get("status", "")),
                                  "user_quote": str(e.get("user_quote") or ""), "decision": str(e["decision"])})


# ---- record builders (same shapes as the live hooks) -----------------------------------------------
def observation_pair(when, sess, name, inp, meta):
    safe = observe_meta.sanitize({"tool_input": inp})["tool_input"]
    base = {"timestamp": ts(when), "tool": name, "session": sess, "project_id": meta[0], "project_name": meta[1],
            "source": "backfill"}
    return [{**base, "event": "tool_start", "input": scrub(json.dumps(safe, ensure_ascii=False)[:5000])},
            {**base, "event": "tool_complete", "output": ""}]


def decision_record(when, sess, cwd, d, meta):
    """Same fields as a user_correction plus the decision itself; text = the user's words when recorded."""
    rec = cc.make_record(sess, cwd, d["user_quote"] or d["decision"])
    rec.update(timestamp=ts(when), event="user_decision", source="backfill", decision_id=d["decision_id"], status=d["status"],
               decision=" ".join(d["decision"].split())[:cc.MAX_CHARS])
    return rec


def is_human_prompt(text: str) -> bool:
    t = text.lstrip()
    return bool(t) and not t.startswith("<") and cc.AUTOMATED_MARK not in t


# ---- run ----------------------------------------------------------------------------------------------
class Run:
    def __init__(self, dry: bool, since: str, use_state: bool, project_root: str = "", rebuild_repeat: bool = False,
                 until: str = ""):
        self.dry, self.since, self.use_state, self.rebuild_repeat = dry, since or "", use_state, rebuild_repeat
        self.until = until or ""  # exclusive; with since it makes a [since, until) window
        self.projects = Projects(project_root)
        self.detector = "default (Kiwi if up, else regex)"
        self.counts = defaultdict(Counter)  # project_id -> counters
        self.files = Counter()
        self.state_path = STORE / "backfill_state.json"
        self.state = json.loads(self.state_path.read_text("utf-8")) if use_state and self.state_path.exists() else {}
        self.buf = defaultdict(lambda: {"corrections": [], "observations": []})
        self.live, self._skipped_live = live_sessions(), set()
        self.origins = written_origins()
        self.prompt_path = STORE / "prompt_index.json"  # origin -> [session, date, masked text]: BM25 corpus
        self.prompts = json.loads(self.prompt_path.read_text("utf-8")) if self.prompt_path.exists() else {}
        self.similar_tokenize, self.similar_min_score = similar.kiwi_tokens, similar.MIN_SCORE  # sessions the live hooks recorded: never replay them (duplicates)
        self.repeat_path = STORE / "repeat_index.json"  # phrase -> sessions, merged across runs
        self.repeat = ri.Index.from_json(self.repeat_path.read_text("utf-8")) if use_state and self.repeat_path.exists() else ri.Index()

    def process(self, path: Path, reader):
        key = str(path) if not (self.since or self.until) else f"{path}|{self.since}|{self.until}"  # state per window
        digest = file_digest(path)
        if self.use_state and key in self.state and self.state[key].get("digest") == digest:
            self.files["unchanged"] += 1
            if not self.rebuild_repeat:
                return
            self.files["reread_for_repeat"] += 1  # repeat index only; corrections/observations stay as they are
            for item in reader(path):
                if item[0] == "prompt" and is_human_prompt(item[4]):
                    self.repeat.add(item[2], item[4])
            return
        self.files["read"] += 1
        n_items = 0
        for item in reader(path):
            n_items += 1
            kind, when, sess, cwd = item[:4]
            origin = item_origin(item)
            if sess in self.live:  # records come from the live hooks; the derived indexes still need the prompt
                if sess not in self._skipped_live:
                    self._skipped_live.add(sess)
                    self.files["live_session_skipped"] += 1
                if kind == "prompt":
                    text = item[4].encode("utf-8", "replace").decode("utf-8")
                    if is_human_prompt(text):
                        self.repeat.add(sess, text)
                        self.prompts[origin] = [sess, ts(when)[:10], cc.make_record(sess, cwd, text)["text"]]
                continue
            if (self.since and ts(when) < self.since) or (self.until and ts(when) >= self.until):
                continue
            meta = self.projects.resolve(cwd)
            c = self.counts[meta[0]]
            if kind == "prompt":
                text = item[4].encode("utf-8", "replace").decode("utf-8")  # lone surrogates cannot be written
                if not is_human_prompt(text):
                    c["prompt_injected"] += 1
                    continue
                c["prompt"] += 1
                self.repeat.add(sess, text)
                self.prompts[origin] = [sess, ts(when)[:10], cc.make_record(sess, cwd, text)["text"]]
                if cc.is_correction(text):
                    if origin in self.origins:
                        c["already_written"] += 1
                        continue
                    self.origins.add(origin)
                    rec = cc.make_record(sess, cwd, text)
                    rec.update(timestamp=ts(when), source="backfill", origin=origin)
                    self.buf[meta[0]]["corrections"].append(rec)
                    c["correction"] += 1
            elif kind == "decision_unsettled":
                c["decision_skipped"] += 1
            elif kind == "decision":
                if origin in self.origins:
                    c["already_written"] += 1
                    continue
                self.origins.add(origin)
                self.buf[meta[0]]["corrections"].append({**decision_record(when, sess, cwd, item[4], meta), "origin": origin})
                c["decision"] += 1
            else:
                if origin in self.origins:
                    c["already_written"] += 1
                    continue
                self.origins.add(origin)
                self.buf[meta[0]]["observations"].extend({**o, "origin": origin} for o in observation_pair(when, sess, item[4], item[5], meta))
                c["tool_use"] += 1
        self.state[key] = {"digest": digest, "items": n_items, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    def flush(self):
        if self.dry:
            return
        STORE.mkdir(parents=True, exist_ok=True)
        with open(STORE / ".observe.lock", "a+b") as g, pc.file_lock(g, 60) as held:
            if not held:
                sys.exit("store is locked by a running hook; retry")
            reg_path = STORE / "projects.json"
            reg = json.loads(reg_path.read_text("utf-8")) if reg_path.exists() else {}
            on_disk = written_origins()  # re-read under the lock: another run may have flushed since we started
            for parts in self.buf.values():
                for name in ("corrections", "observations"):
                    parts[name] = [r for r in parts[name] if r.get("origin") not in on_disk]
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            for pid, parts in self.buf.items():
                pdir = STORE / "projects" / pid if pid != "global" else STORE
                pdir.mkdir(parents=True, exist_ok=True)
                for name in ("corrections", "observations"):
                    if parts[name]:
                        f = pdir / f"{name}.jsonl"
                        if name == "observations" and f.exists() and f.stat().st_size >= MAX_FILE_SIZE_MB * 2**20:
                            (pdir / "observations.archive").mkdir(exist_ok=True)
                            f.rename(pdir / "observations.archive" / f"observations-{time.strftime('%Y%m%d-%H%M%S')}-backfill.jsonl")
                        with f.open("a", encoding="utf-8") as out:
                            out.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in parts[name]))
                if pid != "global":
                    _, pname, root, remote = self.projects.seen[pid]
                    entry = reg.get(pid, {})
                    reg[pid] = {"id": pid, "name": pname, "root": root, "remote": remote,
                                "created_at": entry.get("created_at", now), "last_seen": now}
            write_atomic(reg_path, json.dumps(reg, indent=2, ensure_ascii=False))
            recs = ri.records(self.repeat)
            write_atomic(STORE / "repeated_instructions.jsonl",  # derived: rewritten whole each run
                         "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs))
            self.files["repeated_instructions"] = len(recs)
            if self.prompt_path.exists() and not self.dry:  # merge with what another run wrote meanwhile
                self.prompts = {**json.loads(self.prompt_path.read_text("utf-8")), **self.prompts}
            write_atomic(self.prompt_path, json.dumps(self.prompts, ensure_ascii=False))
            if self.similar_tokenize is None:
                self.files["similar_instructions"] = "skipped (no pinned Kiwi)"
            else:
                docs = sorted({tuple(v) for v in self.prompts.values()}, key=lambda d: (d[1], d[0], d[2]))
                try:
                    sims = similar.pairs(docs, tokenize=self.similar_tokenize, min_score=self.similar_min_score)
                except OSError:  # pinned Kiwi server not reachable: keep the old file, never switch tokenizer
                    self.files["similar_instructions"] = "skipped (Kiwi server unreachable)"
                else:
                    write_atomic(STORE / "similar_instructions.jsonl", "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in sims))
                    self.files["similar_instructions"] = len(sims)
            if self.use_state:  # merge with what another run may have written meanwhile (we hold the lock)
                disk = json.loads(self.state_path.read_text("utf-8")) if self.state_path.exists() else {}
                write_atomic(self.state_path, json.dumps({**disk, **self.state}, indent=1))
                if self.repeat_path.exists() and not self.rebuild_repeat:
                    self.repeat.merge(ri.Index.from_json(self.repeat_path.read_text("utf-8")))
                write_atomic(self.repeat_path, self.repeat.to_json())

    def report(self):
        tot = Counter()
        rows = []
        for pid, c in sorted(self.counts.items(), key=lambda kv: -kv[1]["prompt"]):
            tot.update(c)
            rows.append(f"{self.projects.seen[pid][1][:28]:28} {pid:12} prompts={c['prompt']:6} corrections={c['correction']:5} "
                        f"decisions={c['decision']:4} (unsettled skipped {c['decision_skipped']}) "
                        f"tool_uses={c['tool_use']:7} injected={c['prompt_injected']:6}")
        print(f"files: {dict(self.files)}   mode: {'DRY RUN' if self.dry else 'written to ' + str(STORE)}"
              f"   detector: {self.detector}")
        print("\n".join(rows[:40]) + (f"\n... {len(rows) - 40} more projects" if len(rows) > 40 else ""))
        print(f"TOTAL prompts={tot['prompt']} corrections={tot['correction']} decisions={tot['decision']} tool_uses={tot['tool_use']} injected={tot['prompt_injected']}")


def write_atomic(path: Path, text: str):
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_text(text, "utf-8")
    os.replace(tmp, path)


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def item_origin(item) -> str:
    """Identity of one record = hash of its content, not of where it was read from, so a copied,
    rewritten, truncated or re-ordered transcript never yields the same record twice."""
    kind, when, sess, cwd = item[:4]
    body = json.dumps([kind, when, sess, cwd] + [x if isinstance(x, (str, dict, list)) else str(x) for x in item[4:]],
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8", "surrogatepass")).hexdigest()[:20]


def written_origins() -> set:
    """Origins of records backfill already wrote: the correctness guard (state is only a speed-up)."""
    out = set()
    for f in (list(STORE.glob("*.jsonl")) + list(STORE.glob("observations.archive/*.jsonl"))
              + list(STORE.glob("projects/*/*.jsonl")) + list(STORE.glob("projects/*/observations.archive/*.jsonl"))):
        for line in f.open(encoding="utf-8", errors="replace"):
            if '"origin"' in line:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict) and isinstance(r.get("origin"), str):
                    out.add(r["origin"])
    return out


LIVE_EVENTS = {"tool_start", "tool_complete", "user_correction"}  # what the live hooks write


def live_sessions() -> set:
    """Session ids in records the live hooks wrote (no "source": "backfill")."""
    out = set()
    for f in (list(STORE.glob("*.jsonl")) + list(STORE.glob("observations.archive/*.jsonl"))
              + list(STORE.glob("projects/*/*.jsonl")) + list(STORE.glob("projects/*/observations.archive/*.jsonl"))):
        for line in f.open(encoding="utf-8", errors="replace"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if (isinstance(r, dict) and r.get("session") and r.get("source") != "backfill"
                    and r.get("event") in LIVE_EVENTS):  # derived files (similar pairs, …) also carry "session"
                out.add(r["session"])
    return out


def pin_detector(wait: float = 20.0) -> str:
    """Use ONE detector for the whole run. capture_correction falls back to regex while the Kiwi
    server is down and wakes it in the background, so a run that starts cold would switch from
    regex to Kiwi midway and classify the same text differently (seen on the DDS sample: 2 vs 4).
    Start Kiwi and wait for it; if it never answers, pin regex for every line instead."""
    import kiwi_server
    if not _server_up():
        cc._start_server_detached()
        deadline = time.monotonic() + wait
        while not _server_up() and time.monotonic() < deadline:
            time.sleep(0.2)
    if _server_up():
        ident = _server_identity()
        if ident != kiwi_server.PIN:
            sys.exit(f"backfill: running Kiwi {ident} is not the PIN {kiwi_server.PIN}; use the pinned venv or --regex")
        return "kiwi " + kiwi_server.PIN["kiwipiepy"]
    cc.is_correction = cc.is_correction_regex  # never touch the server again in this run
    return "regex (Kiwi server unavailable)"


def _server_up() -> bool:
    import socket, kiwi_server
    try:
        socket.create_connection((kiwi_server.HOST, kiwi_server.PORT), timeout=0.3).close()
        return True
    except OSError:
        return False


def _server_identity() -> dict:
    import socket, kiwi_server
    with socket.create_connection((kiwi_server.HOST, kiwi_server.PORT), timeout=2) as s:
        s.sendall(b'{"op":"ping"}\n')
        r = json.loads(s.makefile("rb").readline().decode("utf-8"))
    return {k: v for k, v in r.items() if k != "ok"}


def iter_files(paths, source):
    for p in paths:
        p = Path(p).expanduser()
        if p.is_file():
            yield p, (read_codex if p.name.startswith("rollout-") else read_claude)
        elif p.is_dir():
            for f in sorted(p.rglob("*.jsonl")):
                codex = f.name.startswith("rollout-")
                if source == "all" or (source == "codex") == codex:
                    yield f, (read_codex if codex else read_claude)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", help="files or dirs (default: both standard roots)")
    ap.add_argument("--dry-run", action="store_true", help="count only; write nothing")
    ap.add_argument("--since", default="", help="skip records before this UTC date (YYYY-MM-DD)")
    ap.add_argument("--until", default="", help="skip records on/after this UTC date (exclusive); pair with --since for windows")
    ap.add_argument("--source", choices=["all", "claude", "codex"], default="all")
    ap.add_argument("--no-state", action="store_true", help="ignore and do not write backfill_state.json")
    ap.add_argument("--decisions", nargs="*", default=[], metavar="PATH",
                    help="curated decision logs (files or dirs of *.json, e.g. <repo>/decisions); read in addition to paths")
    ap.add_argument("--project-root", default="", metavar="DIR",
                    help="file every record under this project (for logs whose cwd is not a git repo or no longer exists)")
    ap.add_argument("--regex", action="store_true", help="use the regex detector only (no Kiwi server)")
    ap.add_argument("--rebuild-repeat", action="store_true",
                    help="reread files already in backfill_state for the repeat index only (after changing repeat_instr)")
    ap.add_argument("--max-files", type=int, default=0, help="stop after this many files (newest first); 0 = all")
    a = ap.parse_args(argv)
    if hasattr(os, "nice"):
        os.nice(19)  # a full replay reads GBs; never compete with the user's foreground work
    defaults = [r for r, s in ((CLAUDE_ROOT, "claude"), (CODEX_ROOT, "codex")) if a.source in ("all", s)]
    paths = a.paths if (a.paths or a.decisions) else defaults  # --decisions alone replays only the decision logs
    run = Run(a.dry_run, a.since, not a.no_state, a.project_root, a.rebuild_repeat, a.until)
    if a.rebuild_repeat and not a.dry_run:
        run.repeat = ri.Index()  # start the index over; the derived file is rewritten from it
    run.detector = pin_detector() if not a.regex else (setattr(cc, "is_correction", cc.is_correction_regex) or "regex")
    if not run.detector.startswith("kiwi"):
        run.similar_tokenize = None  # BM25 needs the pinned Kiwi tokens; never switch tokenizer silently
    todo = sorted(iter_files(paths, a.source), key=lambda fr: -fr[0].stat().st_mtime)
    for d in a.decisions:
        d = Path(d).expanduser()
        todo += [(f, read_decisions) for f in (sorted(d.rglob("*.json")) if d.is_dir() else [d])]
    if a.max_files:
        todo = todo[:a.max_files]
    t0 = time.monotonic()
    for i, (f, reader) in enumerate(todo, 1):
        try:
            run.process(f, reader)
        except OSError as e:
            run.files["error"] += 1
            print(f"skip {f}: {e}", file=sys.stderr)
        if i % 500 == 0 or i == len(todo):
            print(f"[{i}/{len(todo)} files, {time.monotonic() - t0:.0f}s]", file=sys.stderr, flush=True)
    run.flush()
    run.report()


if __name__ == "__main__":
    main(sys.argv[1:])
