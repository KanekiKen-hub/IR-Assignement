"""Build a positional index from document IDs and preprocessed token sequences."""

from collections.abc import Iterable, Sequence

from src.positional_index import PositionalIndex


ProcessedDocument = tuple[str, Sequence[str]]


def build_positional_index(
    documents: Iterable[ProcessedDocument],
) -> PositionalIndex:
    """Build an in-memory positional index from already-tokenized documents."""
    index = PositionalIndex()
    for document_id, tokens in documents:
        index.add_tokens(document_id, tokens)
    return index
