"""BM25 similar-instruction search (STUDIO-ECC-023, rule tier).

The same instruction comes back in other sessions with different wording; exact n-grams miss it.
Tokens: the pinned Kiwi server (kiwi_server.PIN) keeping content tags, then human-approved synonyms
(synonyms.json), then Okapi BM25 over an inverted index. Same input -> same ranking.
MIN_SCORE is a tier-2 parameter: set from the 2026-10-24 probe (true matches 18-34, a wrong top-1 at 14.5).
"""
import json, math, time
from collections import Counter, defaultdict

import capture_correction as cc  # pinned Kiwi server client, secret/document masking, size cap
import synonyms as syn_mod

K1, B = 1.5, 0.75
MIN_SCORE = 16.0
CONTENT_TAGS = ("NNG", "NNP", "SL", "XR", "VV", "VA")


def kiwi_tokens(text: str) -> list:
    """Content morphemes from the pinned Kiwi server (raises if it is down: no silent tokenizer switch)."""
    return [f.lower() for f, t in cc._tokens_from_server(text[:2000], timeout=5) if t in CONTENT_TAGS and len(f) >= 2]


class Index:
    def __init__(self, docs, tokenize=kiwi_tokens, synonyms=None):
        """docs: [(session, date, text)]"""
        self.docs = list(docs)
        self.syn = synonyms if synonyms is not None else syn_mod.load()
        self.tok = lambda t: [self.syn.canon(w) for w in tokenize(t)]
        self.postings = defaultdict(list)  # term -> [(doc index, tf)]
        self.lens = []
        for i, (_, _, text) in enumerate(self.docs):
            tf = Counter(self.tok(text))
            self.lens.append(sum(tf.values()))
            for w, n in tf.items():
                self.postings[w].append((i, n))
        n = len(self.docs) or 1
        self.avg = (sum(self.lens) / n) or 1.0
        self.idf = {w: math.log(1 + (n - len(p) + 0.5) / (len(p) + 0.5)) for w, p in self.postings.items()}

    def search(self, query: str, k: int = 3, exclude_session: str = ""):
        scores = defaultdict(float)
        for w in set(self.tok(query)):
            for i, tf in self.postings.get(w, ()):
                if self.docs[i][0] == exclude_session:
                    continue
                scores[i] += self.idf[w] * tf * (K1 + 1) / (tf + K1 * (1 - B + B * self.lens[i] / self.avg))
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], self.docs[kv[0]][1], self.docs[kv[0]][2]))
        return [(round(s, 3), self.docs[i][0], self.docs[i][1], self.docs[i][2]) for i, s in ranked[:k]]


BANDS = [(10, 13), (13, 16), (16, 18), (18, 20), (20, 25), (25, 30), (30, 999)]


def choose_threshold(items, target_precision: float, bands=BANDS, positive=("same_instruction",)):
    """The lowest band edge at which the CUMULATIVE precision of everything at or above it reaches the
    target: that is exactly the set the learner would receive with MIN_SCORE at that edge. Cumulative, not
    per-band, so one noisy band of ~10 samples cannot block all bands below it. None if no edge qualifies."""
    chosen = None
    for lo, _ in reversed(bands):
        above = [i for i in items if i["score"] >= lo]
        if not above:
            continue
        if sum(i["label"] in positive for i in above) / len(above) >= target_precision:
            chosen = lo
    return chosen


def _masked(text: str) -> str:
    return cc.make_record("", "", text)["text"]


def pairs(docs, tokenize=kiwi_tokens, synonyms=None, min_score: float = MIN_SCORE) -> list:
    """For each prompt, its best match in ANOTHER session if the score clears min_score."""
    idx = Index(docs, tokenize=tokenize, synonyms=synonyms)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    out = []
    for sess, date, text in idx.docs:
        hit = idx.search(text, k=1, exclude_session=sess)
        if hit and hit[0][0] >= min_score:
            score, msess, mdate, mtext = hit[0]
            out.append({"timestamp": now, "event": "user_similar_instruction", "session": sess, "date": date,
                        "text": _masked(text), "match_session": msess, "match_date": mdate,
                        "match_text": _masked(mtext), "score": score})
    return out
