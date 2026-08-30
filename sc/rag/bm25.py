"""Okapi BM25 lexical retrieval.

Semantic search alone is the wrong tool for this corpus. Editors search for
identifiers - VAR-01B, MKA-4102, RUL-A05, DOC-01 v2 - and an embedding model
maps VAR-01A and VAR-01B to almost the same point in vector space. It has no
way to know that one is rated at 45 W and the other at 65 W, which is precisely
the distinction the whole finale turns on.

BM25 does not have that problem: an exact token match on VAR-01B scores, and
VAR-01A does not. Running both and fusing the rankings gives conceptual recall
from the embeddings and identifier precision from BM25.

Implemented directly rather than pulled from a library - it is forty lines of
arithmetic, and the lab install stays small.
"""

from __future__ import annotations

import math
import re
from collections import Counter

K1 = 1.5   # term-frequency saturation
B = 0.75   # length normalisation

# Keeps hyphenated identifiers whole: "VAR-01B" is one token, not "var" + "01b".
# Without this every variant id collapses to the same two tokens and lexical
# search becomes useless on exactly the queries that need it most.
_TOKEN = re.compile(r"[a-z0-9]+(?:[-.][a-z0-9]+)*")

# Common English words plus terms that appear in nearly every document here.
# "product" or "channel" carry no discriminating signal in this corpus.
_STOPWORDS = frozenset("""
a an and are as at be been by for from has have if in into is it its of on or
that the their then there these they this to was were which will with
""".split())


def tokenize(text: str) -> list[str]:
    tokens = _TOKEN.findall(text.lower())
    out: list[str] = []
    for token in tokens:
        if token in _STOPWORDS or len(token) < 2:
            continue
        out.append(token)
        # Also index the parts of an identifier so "VAR" alone still matches,
        # while the full "var-01b" keeps its precision.
        if "-" in token or "." in token:
            out.extend(p for p in re.split(r"[-.]", token)
                       if len(p) > 1 and p not in _STOPWORDS)
    return out


class BM25:
    """A static index over a fixed chunk list. Rebuilt, never mutated."""

    def __init__(self, documents: list[str]) -> None:
        self.docs = [tokenize(d) for d in documents]
        self.n = len(self.docs)
        self.lengths = [len(d) for d in self.docs]
        self.avg_length = (sum(self.lengths) / self.n) if self.n else 0.0

        self.term_freq: list[Counter] = [Counter(d) for d in self.docs]
        doc_freq: Counter = Counter()
        for tf in self.term_freq:
            doc_freq.update(tf.keys())

        # Standard BM25 IDF with the +0.5 smoothing, floored so that a term
        # appearing in most documents cannot contribute a negative score.
        self.idf = {
            term: max(1e-6, math.log(1 + (self.n - df + 0.5) / (df + 0.5)))
            for term, df in doc_freq.items()
        }

    def scores(self, query: str) -> list[float]:
        terms = tokenize(query)
        out = [0.0] * self.n
        if not terms or not self.n:
            return out

        for i, tf in enumerate(self.term_freq):
            length_norm = K1 * (1 - B + B * self.lengths[i]
                                / (self.avg_length or 1.0))
            total = 0.0
            for term in terms:
                freq = tf.get(term)
                if not freq:
                    continue
                total += self.idf.get(term, 0.0) * (freq * (K1 + 1)) / (freq + length_norm)
            out[i] = total
        return out

    def rank(self, query: str, top_k: int = 20,
             allowed: set[int] | None = None) -> list[tuple[int, float]]:
        scored = [
            (i, s) for i, s in enumerate(self.scores(query))
            if s > 0 and (allowed is None or i in allowed)
        ]
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return scored[:top_k]
