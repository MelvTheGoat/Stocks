"""Turning the database into passages that can be retrieved and cited.

The retrieval baseline needs something to retrieve. There are no filings in this
project -- the NGX reports were ruled out by the exchange's terms -- so the
corpus is written out of the database itself: one short sentence per trading day,
per dividend, per corporate action, and one card per security.

Writing records as sentences rather than rows is the point. It lets a lexical
index match a question's own wording, and it means a retrieved passage can be
quoted back to a reader as a citation without further formatting.

This is also what makes the baseline a fair opponent for the agent rather than a
straw man. The agent gets a price lookup tool; the baseline gets the same facts
as text. Whatever difference the experiment finds is then attributable to having
tools rather than to having been handed less information.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date

from stockagent.data.store import MarketStore
from stockagent.retrieval.bm25 import BM25Index, Document

# How a currency is written into a passage, so a question mentioning naira or
# dollars can match on it.
_MONEY_WORD = {"USD": "dollars", "NGN": "naira"}


def daily_documents(
    store: MarketStore, market: str, *, since: date | None = None
) -> list[Document]:
    rows = store.query(
        """
        SELECT ticker, day, open, high, low, close, volume, currency
        FROM bars
        WHERE market = ? AND (? IS NULL OR day >= ?)
        ORDER BY ticker, day
        """,
        [market, since, since],
    )
    return [
        Document(
            id=f"bar:{market}:{ticker}:{day.isoformat()}",
            text=(
                f"{ticker} on {day.isoformat()}: opened {open_:.4f}, high {high:.4f}, "
                f"low {low:.4f}, closed {close:.4f} {_MONEY_WORD.get(currency, currency)}, "
                f"volume {volume}."
            ),
            source=f"bars:{market}:{ticker}:{day.isoformat()}",
            meta={"ticker": ticker, "market": market, "day": day, "kind": "bar"},
        )
        for ticker, day, open_, high, low, close, volume, currency in rows
    ]


def dividend_documents(store: MarketStore, market: str) -> list[Document]:
    rows = store.query(
        """
        SELECT ticker, ex_date, amount, currency, paid_on
        FROM dividends WHERE market = ? ORDER BY ticker, ex_date
        """,
        [market],
    )
    documents = []
    for ticker, ex_date, amount, currency, paid_on in rows:
        paid = f" It was paid on {paid_on.isoformat()}." if paid_on else ""
        documents.append(
            Document(
                id=f"dividend:{market}:{ticker}:{ex_date.isoformat()}",
                text=(
                    f"{ticker} went ex-dividend on {ex_date.isoformat()} with a dividend of "
                    f"{amount:.4f} {_MONEY_WORD.get(currency, currency)} per share.{paid}"
                ),
                source=f"dividends:{market}:{ticker}:{ex_date.isoformat()}",
                meta={"ticker": ticker, "market": market, "day": ex_date, "kind": "dividend"},
            )
        )
    return documents


def action_documents(store: MarketStore, market: str) -> list[Document]:
    rows = store.query(
        """
        SELECT ticker, effective_date, factor, kind
        FROM actions WHERE market = ? ORDER BY ticker, effective_date
        """,
        [market],
    )
    documents = []
    for ticker, day, factor, kind in rows:
        word = "bonus issue" if kind == "bonus" else "share split"
        direction = "consolidation" if factor < 1 else "split"
        documents.append(
            Document(
                id=f"action:{market}:{ticker}:{day.isoformat()}",
                text=(
                    f"{ticker} had a {word} effective {day.isoformat()}. Each share held "
                    f"before became {factor:g} shares afterwards, so prices quoted before "
                    f"that date must be divided by {factor:g} to compare them with later "
                    f"ones. This was a {direction}."
                ),
                source=f"actions:{market}:{ticker}:{day.isoformat()}",
                meta={"ticker": ticker, "market": market, "day": day, "kind": "action"},
            )
        )
    return documents


def security_documents(store: MarketStore, market: str) -> list[Document]:
    """One card per security, carrying its names and the range we hold.

    This is what answers "what ticker does Apple trade under" and, just as
    importantly, what lets a question using a former name find the right company.
    """
    rows = store.query(
        "SELECT ticker, name, currency FROM securities WHERE market = ? ORDER BY ticker",
        [market],
    )
    coverage = {
        ticker: (first, last, count)
        for ticker, first, last, count in store.query(
            """
            SELECT ticker, min(day), max(day), count(DISTINCT day)
            FROM bars WHERE market = ? GROUP BY ticker
            """,
            [market],
        )
    }
    aliases: dict[str, list[str]] = {}
    for ticker, text in store.query(
        "SELECT ticker, text FROM aliases WHERE market = ? ORDER BY ticker", [market]
    ):
        aliases.setdefault(ticker, []).append(text)

    documents = []
    for ticker, name, currency in rows:
        held = coverage.get(ticker)
        span = (
            f" Data runs from {held[0].isoformat()} to {held[1].isoformat()}, "
            f"{held[2]} trading days."
            if held
            else " No price data is held for it."
        )
        former = aliases.get(ticker)
        also = f" It has also been known as {', '.join(former)}." if former else ""
        documents.append(
            Document(
                id=f"security:{market}:{ticker}",
                text=(
                    f"{name} trades on the {market} market under the ticker {ticker}, "
                    f"quoted in {_MONEY_WORD.get(currency, currency)}.{also}{span}"
                ),
                source=f"securities:{market}:{ticker}",
                meta={"ticker": ticker, "market": market, "kind": "security"},
            )
        )
    return documents


def build_documents(
    store: MarketStore,
    market: str = "US",
    *,
    since: date | None = None,
    extra: Iterable[Document] = (),
) -> list[Document]:
    """Every passage for one market.

    `extra` exists for the prompt-injection cases, which plant a document with an
    instruction hidden in it. They go through the same index as everything else
    on purpose: a retrieval path that treats planted documents specially would
    not be testing anything.
    """
    return [
        *security_documents(store, market),
        *action_documents(store, market),
        *dividend_documents(store, market),
        *daily_documents(store, market, since=since),
        *extra,
    ]


def build_index(
    store: MarketStore,
    market: str = "US",
    *,
    since: date | None = None,
    extra: Iterable[Document] = (),
    k1: float = 1.5,
    b: float = 0.75,
) -> BM25Index:
    return BM25Index(build_documents(store, market, since=since, extra=extra), k1=k1, b=b)


def planted_document(doc_id: str, visible_text: str, instruction: str) -> Document:
    """A document with an instruction hidden inside otherwise ordinary text.

    Built here rather than in the test so the injection cases and the corpus
    agree on what a planted document looks like.
    """
    return Document(
        id=f"planted:{doc_id}",
        text=f"{visible_text}\n\n{instruction}",
        source=f"planted:{doc_id}",
        meta={"kind": "planted", "instruction": instruction},
    )


def sources_of(documents: Sequence[Document]) -> list[str]:
    return [document.source for document in documents]
