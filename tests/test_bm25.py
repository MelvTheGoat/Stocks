"""BM25: the three properties it exists to have, plus its edges."""

import pytest

from stockagent.retrieval.bm25 import BM25Index, Document, tokenize


def document(doc_id: str, text: str, **meta) -> Document:
    return Document(id=doc_id, text=text, source=f"src:{doc_id}", meta=meta)


# --- tokenising -------------------------------------------------------------


def test_words_are_lowercased_and_stopwords_dropped():
    assert tokenize("What was the closing price") == ["closing", "price"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # A date has to survive as one token, or a question about a specific day
        # cannot match the record for that day.
        ("closed on 2026-09-25", ["closed", "2026-09-25"]),
        ("price 241.30", ["price", "241.30"]),
        ("p/e ratio", ["p/e", "ratio"]),
    ],
)
def test_dates_decimals_and_ratios_stay_whole(text, expected):
    assert tokenize(text) == expected


def test_price_field_names_are_not_treated_as_stopwords():
    # "high", "low", "close" and "open" are all columns here.
    assert tokenize("high low open close") == ["high", "low", "open", "close"]


def test_empty_text_yields_nothing():
    assert tokenize("") == []
    assert tokenize(None) == []


# --- the three properties ---------------------------------------------------


def test_more_mentions_rank_higher():
    index = BM25Index(
        [
            document("a", "dividend"),
            document("b", "dividend dividend dividend"),
        ]
    )
    ranked = index.search("dividend")
    assert [hit.document.id for hit in ranked] == ["b", "a"]


def test_the_gain_from_extra_mentions_diminishes():
    index = BM25Index(
        [
            document("one", "dividend"),
            document("two", "dividend dividend"),
            document("ten", "dividend " * 10),
        ]
    )
    scores = {hit.document.id: hit.score for hit in index.search("dividend", limit=10)}

    first_step = scores["two"] - scores["one"]
    later_step = scores["ten"] - scores["two"]
    # Eight more mentions buy less than the second one did.
    assert later_step < first_step * 8


def test_a_rare_term_weighs_more_than_a_common_one():
    common = [document(f"c{i}", "apple price") for i in range(20)]
    index = BM25Index([*common, document("rare", "apple greenshoe")])

    assert index.inverse_document_frequency("greenshoe") > index.inverse_document_frequency("apple")


def test_a_term_in_every_document_still_scores_above_zero():
    # A negative weight would let a document that matched nothing outrank one
    # that matched, which is a baffling ranking to debug.
    index = BM25Index([document(f"d{i}", "apple") for i in range(10)])
    assert index.inverse_document_frequency("apple") > 0


def test_a_short_document_beats_a_long_one_on_the_same_mention():
    index = BM25Index(
        [
            document("short", "apple dividend"),
            document("long", "apple dividend " + "filler words about other things " * 20),
        ]
    )
    assert [hit.document.id for hit in index.search("apple dividend")] == ["short", "long"]


def test_length_normalisation_can_be_turned_off():
    # With b=0 length stops mattering, so the two tie on term frequency and the
    # ordering falls back to the id.
    index = BM25Index(
        [
            document("short", "apple"),
            document("long", "apple " + "filler " * 50),
        ],
        b=0.0,
    )
    scores = [hit.score for hit in index.search("apple", limit=10)]
    assert scores[0] == pytest.approx(scores[1])


# --- searching --------------------------------------------------------------


def test_documents_matching_nothing_are_left_out():
    index = BM25Index([document("a", "apple dividend"), document("b", "microsoft revenue")])
    hits = index.search("apple")

    assert [hit.document.id for hit in hits] == ["a"]


def test_a_query_with_no_match_returns_nothing():
    # An empty result is the signal that lets the layer above say it does not
    # know, instead of reaching for the nearest passage.
    index = BM25Index([document("a", "apple dividend")])
    assert index.search("jollof rice") == []


def test_a_query_of_only_stopwords_returns_nothing():
    index = BM25Index([document("a", "apple dividend")])
    assert index.search("what is the of and") == []


def test_searching_an_empty_index_returns_nothing():
    assert BM25Index().search("apple") == []


def test_the_limit_is_respected():
    index = BM25Index([document(f"d{i}", "apple") for i in range(10)])
    assert len(index.search("apple", limit=3)) == 3


def test_matched_terms_are_reported():
    index = BM25Index([document("a", "apple paid a dividend in March")])
    (hit,) = index.search("apple dividend microsoft")

    assert set(hit.matched) == {"apple", "dividend"}


def test_ties_are_broken_deterministically():
    # Two runs over the same corpus must give the same order, or a result is not
    # reproducible.
    docs = [document("b", "apple"), document("a", "apple"), document("c", "apple")]
    first = [hit.document.id for hit in BM25Index(docs).search("apple", limit=3)]
    second = [hit.document.id for hit in BM25Index(list(reversed(docs))).search("apple", limit=3)]

    assert first == second == ["a", "b", "c"]


def test_documents_carry_their_source_and_metadata_through():
    index = BM25Index([document("a", "apple dividend", ticker="AAPL")])
    (hit,) = index.search("dividend")

    assert hit.document.source == "src:a"
    assert hit.document.meta["ticker"] == "AAPL"


def test_documents_can_be_added_after_construction():
    index = BM25Index()
    index.add_all([document("a", "apple"), document("b", "microsoft")])

    assert len(index) == 2
    assert index.search("microsoft")[0].document.id == "b"


def test_the_average_length_reflects_what_was_indexed():
    index = BM25Index([document("a", "one two"), document("b", "one two three four")])
    assert index.average_length == pytest.approx(3.0)


def test_the_average_length_of_an_empty_index_is_zero():
    assert BM25Index().average_length == 0.0


def test_a_date_in_a_question_finds_the_record_for_that_day():
    index = BM25Index(
        [
            document("d1", "AAPL closed at 241.30 on 2026-09-24"),
            document("d2", "AAPL closed at 245.10 on 2026-09-25"),
        ]
    )
    (top, *_) = index.search("What did AAPL close at on 2026-09-25?")

    assert top.document.id == "d2"
