# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# MODIFIED (decision-labeling-studio, 2026-10-24): `assert_no_grader_verdicts` and
# `assert_tree_has_no_grader_verdicts` are taken from google-research/harness2
# `harness2/core/context.py` (see SOURCE.txt for commit and line ranges). Changes: the
# marker list is replaced by this project's answer-side vocabulary (`MARKERS`), matching
# is case-insensitive, messages are shortened. `assert_records_metadata_only` is new.
"""Leak tripwire for ecc-clv2: nothing but metadata may reach a model.

The capture boundary (observe_meta.sanitize, capture_correction.MAX_CHARS) is the defence.
This is the tripwire on the two places records are handed to a model (learn_now's analysis
file, eval_loop's judge packet). If it fires, find the read path that produced the content;
do not widen around it.
"""
from pathlib import Path
from typing import Iterable, Mapping, Sequence

# Answer-side vocabulary. eval_loop.ANSWER_SIDE (rule R3) is built from this same tuple.
MARKERS: tuple[str, ...] = ("결과서", "검토결과", "정답", "silver", "gold_label", "gold label")

_MARKER_SCAN_SUFFIXES = frozenset({".md", ".txt", ".json", ".jsonl", ".csv", ".tsv", ".yaml", ".yml", ".html",
                                   ".htm", ".log", ".py", ".js", ".sh", ".xml", ".ini", ".toml", ".patch", ".diff", ""})

# Record fields that can only ever hold content, never metadata. Must be empty or absent.
CONTENT_FIELDS = ("output", "raw", "tool_response", "toolUseResult", "content")
MAX_FIELD_CHARS = 5000  # observe.sh's own cap on serialized input


def _find(markers: Sequence[str], s: str):
    low = s.lower()
    for m in markers:
        if m.lower() in low:
            return m, low.index(m.lower())
    return None


def assert_no_grader_verdicts(root: "Path | str", markers: Sequence[str] = MARKERS) -> None:
    """Refuse a directory containing answer-side material, by file name and by content."""
    root = Path(root)
    if not markers or not root.is_dir():
        return
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        hit = _find(markers, rel)
        if hit:
            raise ValueError(f"leak: {rel!r} has answer-side marker {hit[0]!r} in its NAME")
        if p.suffix.lower() not in _MARKER_SCAN_SUFFIXES:
            continue
        try:
            body = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hit = _find(markers, body)
        if hit:
            m, where = hit
            raise ValueError(f"leak: {rel!r} contains answer-side marker {m!r} at offset {where} "
                             f"({body[max(0, where - 60): where + 120]!r})")


def assert_tree_has_no_grader_verdicts(tree: Mapping[str, str], markers: Sequence[str] = MARKERS) -> None:
    """The same tripwire on an in-memory tree (rel -> body)."""
    for rel in sorted(tree):
        hit = _find(markers, rel)
        if hit:
            raise ValueError(f"leak: {rel!r} has answer-side marker {hit[0]!r} in its NAME")
        if Path(rel).suffix.lower() not in _MARKER_SCAN_SUFFIXES:
            continue
        body = str(tree[rel])
        hit = _find(markers, body)
        if hit:
            m, where = hit
            raise ValueError(f"leak: {rel!r} contains answer-side marker {m!r} at offset {where} "
                             f"({body[max(0, where - 60): where + 120]!r})")


def assert_records_metadata_only(records: Iterable[Mapping]) -> None:
    """Our boundary check for observation/correction records before they reach a model:
    content fields must be empty, no field may exceed MAX_FIELD_CHARS, and content fields
    (never paths or the user's own words) must carry no answer-side marker."""
    tree = {}
    for i, rec in enumerate(records):
        for k, v in rec.items():
            if isinstance(v, str) and len(v) > MAX_FIELD_CHARS:
                raise ValueError(f"leak: record {i} field {k!r} is {len(v)} chars (> {MAX_FIELD_CHARS})")
        for k in CONTENT_FIELDS:
            v = rec.get(k)
            if v not in (None, ""):
                tree[f"record{i}.{k}.txt"] = str(v)
    if tree:
        rel = next(iter(sorted(tree)))
        try:
            assert_tree_has_no_grader_verdicts(tree)
        except ValueError:
            raise
        raise ValueError(f"leak: {rel!r} is a content field and is not empty ({tree[rel][:80]!r})")
