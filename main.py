"""Command-line workflows for Reuters retrieval and Telugu Wikipedia indexing."""

import argparse
import re
import time
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

from src.dataset_loader import DatasetLoader
from src.evaluation import approximate_storage_bytes
from src.disk_index_builder import DiskIndexBuildStats, build_disk_index
from src.index_builder import ProcessedDocument
from src.inverted_index import InvertedIndex
from src.positional_index import PositionalIndex
from src.preprocessor import Preprocessor
from src.search_engine import SearchEngine
from src.storage_manager import StorageManager
from src.wikipedia_dataset_loader import WikipediaDatasetLoader
from src.wikitext_cleaner import WikipediaTextCleaner


RESULT_LIMIT = 20
SNIPPET_LENGTH = 200
_BOOLEAN_OPERATOR = re.compile(r"\b(AND|OR)\b", flags=re.IGNORECASE)


# Reuters in-memory search workflow
def build_indexes(
    documents: Iterable[Mapping[str, str]],
) -> tuple[InvertedIndex, PositionalIndex, float]:
    """Build both indexes in one pass and return their combined build time."""
    preprocessor = Preprocessor()
    inverted_index = InvertedIndex(preprocessor)
    positional_index = PositionalIndex(preprocessor)

    start = time.perf_counter()
    document_count = 0
    for document in documents:
        inverted_index.add_document(document)
        positional_index.add_document(document)
        document_count += 1
    elapsed = time.perf_counter() - start

    if document_count != inverted_index.document_count:
        raise RuntimeError("The document source contains duplicate document IDs.")
    if inverted_index.document_count != positional_index.document_count:
        raise RuntimeError("The inverted and positional indexes have different document counts.")

    return inverted_index, positional_index, elapsed


def run_cli(
    loader: DatasetLoader,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> None:
    """Build the Reuters indexes, then accept interactive queries until exit."""
    output_fn("=== Reuters Information Retrieval System ===")
    output_fn("Building indexes from the Reuters corpus...")
    inverted_index, positional_index, build_seconds = build_indexes(
        loader.iter_documents()
    )
    engine = SearchEngine(inverted_index, positional_index)
    storage_bytes = approximate_storage_bytes(inverted_index, positional_index)

    output_fn(f"Documents indexed: {inverted_index.document_count}")
    output_fn(f"Unique terms: {inverted_index.unique_term_count}")
    output_fn(f"Total term occurrences: {positional_index.total_term_occurrences}")
    output_fn(f"Index construction time: {build_seconds:.3f} seconds")
    output_fn(
        "Approximate index storage: "
        f"{storage_bytes:,} bytes ({storage_bytes / (1024 * 1024):.2f} MiB)"
    )

    while True:
        query = input_fn("\nEnter query (or q to quit): ").strip()
        if query.lower() in {"q", "quit", "exit"}:
            output_fn("Goodbye.")
            return
        if not query:
            output_fn("Please enter a non-empty query.")
            continue

        output_fn("Search type: 1) Keyword  2) Boolean  3) Phrase")
        search_type = input_fn("Choose search type (1-3): ").strip()
        if search_type not in {"1", "2", "3"}:
            output_fn("Invalid search type. Choose 1, 2, or 3.")
            continue

        if search_type == "3":
            phrase = (
                query[1:-1]
                if query.startswith('"') and query.endswith('"')
                else query
            )
            query_to_search = f'"{phrase}"'
        else:
            query_to_search = query
            if search_type == "1":
                terms = positional_index.preprocessor.process(query)
                if len(terms) != 1 or _BOOLEAN_OPERATOR.search(query):
                    output_fn("Keyword search requires exactly one term.")
                    continue
            elif not _BOOLEAN_OPERATOR.search(query):
                output_fn("Boolean search requires two terms joined by AND or OR.")
                continue

        try:
            results = engine.search(query_to_search)
        except ValueError as error:
            output_fn(f"Invalid query: {error}")
            continue

        output_fn(f"Search type: {('Keyword', 'Boolean', 'Phrase')[int(search_type) - 1]}")
        output_fn(f"Results found: {len(results)}")
        if not results:
            continue

        document_ids = sorted(results)
        for document_id in document_ids[:RESULT_LIMIT]:
            document = loader.get_document(document_id)
            snippet = " ".join(document["text"].split())
            if len(snippet) > SNIPPET_LENGTH:
                snippet = snippet[:SNIPPET_LENGTH].rstrip() + "..."
            output_fn(f"- {document_id}: {snippet}")

        if len(document_ids) > RESULT_LIMIT:
            output_fn(
                f"Showing the first {RESULT_LIMIT} of {len(document_ids)} results."
            )


# Telugu Wikipedia disk-index workflow
def run_wikipedia_index_cli(
    dump_path: str | Path,
    max_articles: int = 100,
    storage_dir: str | Path = "storage",
    *,
    build_index: bool = True,
    verify: bool = False,
    buffer_record_limit: int = 50_000,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] = print,
) -> StorageManager:
    """Build or reopen the disk-backed Wikipedia index and inspect terms."""
    read_input = input_fn if input_fn is not None else input
    destination = Path(storage_dir)
    stats: DiskIndexBuildStats | None = None
    loader: WikipediaDatasetLoader | None = None
    if build_index:
        loader = WikipediaDatasetLoader(dump_path, max_articles=max_articles)
    else:
        destination.mkdir(parents=True, exist_ok=True)

    cleaner = WikipediaTextCleaner()
    preprocessor = Preprocessor()

    if build_index:
        assert loader is not None

        def processed_documents() -> Iterable[ProcessedDocument]:
            for document in loader.iter_documents():
                cleaned_text = cleaner.clean(document["text"])
                yield document["document_id"], preprocessor.process(cleaned_text)

        last_reported = 0

        def report_progress(documents_processed: int, total_tokens: int) -> None:
            nonlocal last_reported
            if documents_processed - last_reported >= 500:
                output_fn(
                    f"Indexed {documents_processed} articles; "
                    f"{total_tokens} tokens processed."
                )
                last_reported = documents_processed

        stats = build_disk_index(
            processed_documents(),
            destination,
            buffer_record_limit=buffer_record_limit,
            preprocessor=preprocessor,
            progress_callback=report_progress,
        )

    index = StorageManager(destination, preprocessor=preprocessor)
    output_fn(f"Articles indexed: {index.document_count}")
    output_fn(f"Total tokens: {index.total_tokens}")
    output_fn(f"Vocabulary size: {index.unique_term_count}")
    output_fn(f"Total term occurrences: {index.total_term_occurrences}")
    if loader is not None:
        output_fn(f"Pages encountered: {loader.pages_encountered}")
        output_fn(f"Skipped pages: {loader.articles_skipped}")
        output_fn(f"Skip reasons: {loader.skipped_by_reason}")
    if stats is not None:
        output_fn(f"Indexing time: {stats.indexing_seconds:.3f} seconds")
        output_fn(f"Vocabulary file bytes: {stats.vocabulary_file_bytes}")
        output_fn(f"Postings file bytes: {stats.postings_file_bytes}")
        output_fn(f"Vocabulary memory estimate: {stats.vocabulary_memory_bytes}")
        output_fn(f"Temporary runs created: {stats.temporary_run_count}")
        output_fn(f"Peak temporary build bytes: {stats.temporary_bytes_peak}")
        output_fn(f"Peak buffered records: {stats.buffer_records_peak}")
    output_fn(f"Postings path: {index.postings_path}")

    if verify:
        output_fn(f"Verification: {index.verify()}")

    while True:
        query = read_input("\nEnter Telugu term(s) (or q to quit): ").strip()
        if query.lower() in {"q", "quit", "exit"}:
            output_fn("Goodbye.")
            return index
        terms = preprocessor.process(query)
        if not terms:
            output_fn("Please enter a non-empty term.")
            continue

        output_fn(f"Query: {query}")
        for term in terms:
            output_fn(f"Term: {term}")
            statistics = index.get_term_statistics(term)
            if statistics is None:
                output_fn(f"Unknown term: {term}")
                continue

            output_fn(f"CF: {statistics['cf']}")
            output_fn(f"DF: {statistics['df']}")
            output_fn("Postings:")
            for document_id, positions in index.get_postings(term).items():
                output_fn(f"{document_id}: {positions}")


def main(argv: list[str] | None = None) -> None:
    """Build the disk-backed Wikipedia index or load an existing one."""
    project_root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Telugu Wikipedia positional index")
    parser.add_argument(
        "--dump",
        type=Path,
        default=project_root / "tewiki-latest-pages-articles.xml.bz2",
        help="Path to the compressed Telugu Wikipedia XML dump.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5000,
        help="Maximum valid articles to index (default: 5000).",
    )
    parser.add_argument(
        "--storage",
        type=Path,
        default=project_root / "storage",
        help="Index directory containing the current manifest and generations.",
    )
    parser.add_argument(
        "--load-existing",
        action="store_true",
        help="Open the existing index rather than rebuilding it.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify every postings record after building or loading.",
    )
    parser.add_argument(
        "--buffer-record-limit",
        type=int,
        default=50_000,
        help="Maximum intermediate term/document records held before flushing.",
    )
    arguments = parser.parse_args(argv)
    if arguments.limit < 1:
        parser.error("--limit must be a positive integer.")
    if not arguments.load_existing and not arguments.dump.is_file():
        parser.error(f"Wikipedia dump not found: {arguments.dump}")
    run_wikipedia_index_cli(
        arguments.dump,
        max_articles=arguments.limit,
        storage_dir=arguments.storage,
        build_index=not arguments.load_existing,
        verify=arguments.verify,
        buffer_record_limit=arguments.buffer_record_limit,
    )


if __name__ == "__main__":
    main()
