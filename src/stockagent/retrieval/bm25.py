"""BM25, implemented here rather than imported.

BM25 ranks documents against a query by three ideas, and it is worth naming them
because each one shows up in the tests:

1. A document mentioning a query term more times is more relevant, but with
   diminishing returns. The tenth mention of "dividend" says much less than the
   second. `k1` sets how fast the returns diminish.
2. A term appearing in few documents is more informative than one appearing in
   most. That is the inverse document frequency.
3. A long document mentioning a term once is less about that term than a short
   one mentioning it once, so length is normalised. `b` sets how strongly.

The defaults are the usual ones. They are exposed because a corpus of one-line
price records behaves quite differently from a corpus of filings, and tuning them
is a legitimate experiment rather than a magic number.

A deliberate limitation: matching is exact on lowercased word stems only in the
sense that no stemmer is used. "dividends" does not match "dividend". For a
corpus this project generates itself that is fine, and a stemmer would be one
more thing whose behaviour has to be explained when a result moves.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

_WORD = re.compile(r"[a-z0-9][a-z0-9.\-/]*", re.IGNORECASE)

# Words carrying no topic signal. Kept short on purpose: an aggressive list
# removes terms that matter in this domain ("high", "low", "close", "open" are
# all price fields).
STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "did", "do",
        "does", "for", "from", "had", "has", "have", "how", "i", "in", "is",
        "it", "its", "me", "of", "on", "or", "s", "that", "the", "their",
        "there", "this", "to", "was", "were", "what", "when", "which", "who",
        "why", "with", "you", "your",
    }
)


def tokenize(text: str) -> list[str]:
    """Lowercased word tokens, with stopwords removed.

    Dots, hyphens and slashes are kept inside a token so that dates
    (2026-09-25), decimals (241.30) and ratios (p/e) survive as single terms.
    Those are exactly the tokens a question about a specific day needs to match.
    """
    return [
        token
        for token in (match.group(0).lower() for match in _WORD.finditer(text or ""))
        if token not in STOPWORDS
    ]


@dataclass(frozen=True)
class Document:
    """A retrievable passage.

    `source` is what a citation points at, so it travels with the text rather
    than being looked up later.
    """

    id: str
    text: str
    source: str = ""
    # Anything the caller needs back, such as the ticker a record belongs to.
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Hit:
    document: Document
    score: float
    # Which query terms actually matched, which is what makes a ranking
    # explainable rather than merely reproducible.
    matched: tuple[str, ...]


class BM25Index:
    def __init__(
        self,
        documents: Iterable[Document] = (),
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ):
        self.k1 = k1
        self.b = b
        self._documents: list[Document] = []
        self._tokens: list[list[str]] = []
        self._counts: list[Counter[str]] = []
        self._document_frequency: Counter[str] = Counter()
        self._total_length = 0
        for document in documents:
            self.add(document)

    def add(self, document: Document) -> None:
        tokens = tokenize(document.text)
        counts = Counter(tokens)
        self._documents.append(document)
        self._tokens.append(tokens)
        self._counts.append(counts)
        self._total_length += len(tokens)
        # Document frequency counts documents, not occurrences.
        for term in counts:
            self._document_frequency[term] += 1

    def add_all(self, documents: Iterable[Document]) -> None:
        for document in documents:
            self.add(document)

    def __len__(self) -> int:
        return len(self._documents)

    @property
    def average_length(self) -> float:
        if not self._documents:
            return 0.0
        return self._total_length / len(self._documents)

    def inverse_document_frequency(self, term: str) -> float:
        """How informative a term is.

        The plus one inside the logarithm keeps the value positive even for a
        term in every document. Without it a very common term scores negative
        and can push a document below one that matched nothing at all, which is
        a genuinely confusing ranking to debug.
        """
        total = len(self._documents)
        if total == 0:
            return 0.0
        seen = self._document_frequency.get(term, 0)
        return math.log((total - seen + 0.5) / (seen + 0.5) + 1)

    def score(self, query_terms: Sequence[str], index: int) -> tuple[float, list[str]]:
        counts = self._counts[index]
        length = len(self._tokens[index])
        average = self.average_length or 1.0

        total = 0.0
        matched = []
        for term in query_terms:
            frequency = counts.get(term, 0)
            if frequency == 0:
                continue
            matched.append(term)
            weight = self.inverse_document_frequency(term)
            denominator = frequency + self.k1 * (1 - self.b + self.b * length / average)
            total += weight * (frequency * (self.k1 + 1)) / denominator
        return total, matched

    def search(self, query: str, limit: int = 5) -> list[Hit]:
        """Best matching documents, highest first.

        Documents matching nothing are left out entirely rather than returned
        with a score of zero. An empty result is a useful signal: it tells the
        layer above that the corpus has nothing on this, which is the difference
        between saying so and inventing an answer.
        """
        terms = tokenize(query)
        if not terms or not self._documents:
            return []

        hits = []
        for index in range(len(self._documents)):
            score, matched = self.score(terms, index)
            if score <= 0:
                continue
            hits.append(Hit(document=self._documents[index], score=score, matched=tuple(matched)))

        # Ties broken by document id so the ranking is deterministic. Without
        # this, two runs over the same corpus could return different orders and
        # a result would not be reproducible.
        hits.sort(key=lambda hit: (-hit.score, hit.document.id))
        return hits[:limit]
