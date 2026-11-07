"""Index statistics, query timings, and consistency checks."""

import sys
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from src.dataset_loader import DatasetLoader
from src.inverted_index import InvertedIndex
from src.positional_index import PositionalIndex
from src.preprocessor import Preprocessor
from src.search_engine import SearchEngine


DEFAULT_QUERIES = {
    "single term": "oil",
    "AND": "oil AND prices",
    "OR": "oil OR prices",
    "phrase": '"oil prices"',
}


@dataclass(frozen=True)
class QueryMeasurement:
    """Timing and result count for one search query."""

    query: str
    execution_seconds: float
    result_count: int


@dataclass(frozen=True)
class EvaluationReport:
    """Measured index statistics and search results."""

    documents_processed: int
    unique_terms: int
    total_term_occurrences: int
    index_build_seconds: float
    approximate_storage_bytes: int
    query_measurements: dict[str, QueryMeasurement]
    correctness_checks: dict[str, bool]


def approximate_storage_bytes(*objects: object) -> int:
    """Estimate reachable Python object memory, including nested containers.

    This is an in-process approximation, not serialized index size or peak
    process memory. Shared objects are counted once.
    """
    pending = list(objects)
    seen: set[int] = set()
    total_bytes = 0

    while pending:
        value = pending.pop()
        identity = id(value)
        if identity in seen:
            continue
        seen.add(identity)
        total_bytes += sys.getsizeof(value)

        if isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, (list, tuple, set, frozenset)):
            pending.extend(value)
        elif hasattr(value, "__dict__"):
            pending.append(vars(value))

    return total_bytes


def run_correctness_checks(
    engine: SearchEngine,
    inverted_index: InvertedIndex,
    positional_index: PositionalIndex,
) -> dict[str, bool]:
    """Check search results against index postings and positional evidence."""
    oil_postings = inverted_index.get_postings("oil")
    prices_postings = inverted_index.get_postings("prices")
    phrase_matches = _expected_phrase_matches(positional_index, ["oil", "prices"])
    repeated_matches = _expected_phrase_matches(positional_index, ["oil", "oil"])

    return {
        "single-term retrieval": engine.search("oil") == oil_postings,
        "AND retrieval": engine.search("oil AND prices")
        == oil_postings.intersection(prices_postings),
        "OR retrieval": engine.search("oil OR prices")
        == oil_postings.union(prices_postings),
        "exact phrase retrieval": engine.phrase_positions("oil prices")
        == phrase_matches,
        "repeated phrase terms": engine.phrase_positions("oil oil")
        == repeated_matches,
        "unknown term": engine.search("irunknownterm7f3a") == set(),
        "empty query": engine.search("") == set(),
    }


def evaluate_corpus(
    document_factory: Callable[[], Iterable[Mapping[str, str]]] | None = None,
    queries: Mapping[str, str] | None = None,
) -> EvaluationReport:
    """Build both indexes over Reuters (or a supplied repeatable document source).

    The source is called once. Each document is consumed by both indexes in the
    same pass, keeping raw article text from accumulating in memory.
    """
    if document_factory is None:
        loader = DatasetLoader()
        document_factory = loader.iter_documents

    preprocessor = Preprocessor()
    inverted_index = InvertedIndex(preprocessor)
    positional_index = PositionalIndex(preprocessor)
    build_start = time.perf_counter()
    document_count = 0
    for document in document_factory():
        inverted_index.add_document(document)
        positional_index.add_document(document)
        document_count += 1
    build_seconds = time.perf_counter() - build_start

    if inverted_index.document_count != positional_index.document_count:
        raise RuntimeError("The inverted and positional indexes have different document counts.")
    if document_count != inverted_index.document_count:
        raise RuntimeError("The document source contains duplicate document IDs.")

    engine = SearchEngine(inverted_index, positional_index)
    measurements: dict[str, QueryMeasurement] = {}
    for label, query in (queries or DEFAULT_QUERIES).items():
        query_start = time.perf_counter()
        results = engine.search(query)
        elapsed = time.perf_counter() - query_start
        measurements[label] = QueryMeasurement(query, elapsed, len(results))

    return EvaluationReport(
        documents_processed=document_count,
        unique_terms=inverted_index.unique_term_count,
        total_term_occurrences=positional_index.total_term_occurrences,
        index_build_seconds=build_seconds,
        approximate_storage_bytes=approximate_storage_bytes(
            inverted_index, positional_index
        ),
        query_measurements=measurements,
        correctness_checks=run_correctness_checks(
            engine, inverted_index, positional_index
        ),
    )


def _expected_phrase_matches(
    positional_index: PositionalIndex, terms: list[str]
) -> dict[str, list[int]]:
    """Derive exact phrase starts by checking term positions in each candidate."""
    if not terms:
        return {}
    postings = [positional_index.get_postings(term) for term in terms]
    candidate_ids = set(postings[0])
    for term_postings in postings[1:]:
        candidate_ids.intersection_update(term_postings)

    matches: dict[str, list[int]] = {}
    for document_id in candidate_ids:
        positions_by_term = [
            set(term_postings[document_id]) for term_postings in postings
        ]
        starts = [
            position
            for position in positions_by_term[0]
            if all(
                position + offset in positions
                for offset, positions in enumerate(positions_by_term[1:], start=1)
            )
        ]
        if starts:
            matches[document_id] = sorted(starts)
    return matches
