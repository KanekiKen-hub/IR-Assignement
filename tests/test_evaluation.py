from src.evaluation import evaluate_corpus, run_correctness_checks
from src.inverted_index import InvertedIndex
from src.positional_index import PositionalIndex
from src.preprocessor import Preprocessor
from src.search_engine import SearchEngine


DOCUMENTS = [
    {"document_id": "doc-1", "text": "oil prices oil"},
    {"document_id": "doc-2", "text": "oil shares"},
    {"document_id": "doc-3", "text": "prices"},
]


def document_factory():
    return iter(DOCUMENTS)


def test_evaluation_measures_index_and_query_statistics():
    report = evaluate_corpus(document_factory)

    assert report.documents_processed == 3
    assert report.unique_terms == 3
    assert report.total_term_occurrences == 6
    assert report.index_build_seconds >= 0
    assert report.approximate_storage_bytes > 0
    assert {measurement.query for measurement in report.query_measurements.values()} == {
        "oil",
        "oil AND prices",
        "oil OR prices",
        '"oil prices"',
    }
    assert all(
        measurement.execution_seconds >= 0
        and measurement.result_count >= 0
        for measurement in report.query_measurements.values()
    )


def test_evaluation_correctness_checks_pass_for_small_corpus():
    report = evaluate_corpus(document_factory)

    assert all(report.correctness_checks.values())


def test_correctness_checks_detect_phrase_position_consistency():
    processor = Preprocessor()
    inverted = InvertedIndex(processor)
    positional = PositionalIndex(processor)
    inverted.build(DOCUMENTS)
    positional.build(DOCUMENTS)
    engine = SearchEngine(inverted, positional)

    checks = run_correctness_checks(engine, inverted, positional)

    assert all(checks.values())
    assert checks["exact phrase retrieval"]
