import pytest

from src.inverted_index import InvertedIndex
from src.positional_index import PositionalIndex
from src.preprocessor import Preprocessor
from src.search_engine import SearchEngine


@pytest.fixture
def engine():
    preprocessor = Preprocessor()
    documents = [
        {"document_id": "doc-1", "text": "oil prices rose oil prices oil"},
        {"document_id": "doc-2", "text": "oil shares fell"},
        {"document_id": "doc-3", "text": "prices rose"},
    ]
    inverted = InvertedIndex(preprocessor)
    positional = PositionalIndex(preprocessor)
    inverted.build(documents)
    positional.build(documents)
    return SearchEngine(inverted, positional)


def test_single_term_search_is_case_insensitive(engine):
    assert engine.search("OIL") == {"doc-1", "doc-2"}


def test_boolean_and_uses_postings_intersection(engine):
    assert engine.search("oil AND prices") == {"doc-1"}
    assert engine.search("oil and prices") == {"doc-1"}


def test_boolean_or_uses_postings_union(engine):
    assert engine.search("oil OR prices") == {"doc-1", "doc-2", "doc-3"}


def test_phrase_matches_consecutive_tokens_and_returns_positions(engine):
    assert engine.search('"oil prices"') == {"doc-1"}
    assert engine.phrase_positions("oil prices") == {"doc-1": [0, 3]}
    assert engine.search('"prices rose"') == {"doc-1", "doc-3"}


def test_long_phrase_and_repeated_query_terms(engine):
    assert engine.search('"oil prices rose"') == {"doc-1"}
    assert engine.phrase_positions("oil oil") == {}
    assert engine.search('"oil prices oil"') == {"doc-1"}
    assert engine.phrase_positions("oil prices oil") == {"doc-1": [3]}


def test_unknown_terms_and_empty_queries_return_no_results(engine):
    assert engine.search("unknown") == set()
    assert engine.search('"unknown phrase"') == set()
    assert engine.search("") == set()
    assert engine.search("   ") == set()
    assert engine.phrase_positions("") == {}


@pytest.mark.parametrize(
    "query",
    [
        '"unfinished phrase',
        'unfinished phrase"',
        '""',
        "oil prices",
        "oil AND prices OR shares",
        "AND oil",
        "oil OR ",
        "oil AND \"prices rose\"",
    ],
)
def test_malformed_queries_raise_clear_errors(engine, query):
    with pytest.raises(ValueError):
        engine.search(query)
