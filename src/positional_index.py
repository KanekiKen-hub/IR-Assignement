"""In-memory positional index built from preprocessed documents."""

from collections.abc import Iterable, Mapping, Sequence
from types import MappingProxyType

from src.preprocessor import Preprocessor


class PositionalIndex:
    """In-memory reference index for terms, positions, and CF/DF statistics.

    This implementation keeps all postings in memory. Wikipedia indexing uses
    the separate disk-backed builder for larger collections.
    """

    def __init__(self, preprocessor: Preprocessor | None = None) -> None:
        self._preprocessor = preprocessor or Preprocessor()
        self._postings: dict[str, dict[str, list[int]]] = {}
        self._vocabulary: dict[str, dict[str, int]] = {}
        self._document_ids: set[str] = set()
        self._total_token_count = 0

    @property
    def document_count(self) -> int:
        """Return the number of unique document IDs processed."""
        return len(self._document_ids)

    @property
    def unique_term_count(self) -> int:
        """Return the number of distinct terms in the index."""
        return len(self._vocabulary)

    @property
    def total_term_occurrences(self) -> int:
        """Return the collection frequency summed over all terms."""
        return self._total_token_count

    @property
    def total_token_count(self) -> int:
        """Return the number of tokens indexed across all documents."""
        return self._total_token_count

    @property
    def vocabulary(self) -> Mapping[str, Mapping[str, int]]:
        """Return read-only CF/DF metadata, separate from positional postings."""
        return MappingProxyType(
            {
                term: MappingProxyType(statistics)
                for term, statistics in self._vocabulary.items()
            }
        )

    @property
    def preprocessor(self) -> Preprocessor:
        """Return the preprocessor used to build the index."""
        return self._preprocessor

    def build(self, documents: Iterable[Mapping[str, str]]) -> None:
        """Build from documents with ``document_id`` and raw ``text`` fields.

        Positions are zero-based indexes into the processed token sequence.
        Calling ``build`` again replaces the existing index.
        """
        self.clear()

        for document in documents:
            self.add_document(document)

    def add_document(self, document: Mapping[str, str]) -> None:
        """Preprocess and add one raw-text document to the current index."""
        document_id = document["document_id"]
        tokens = self._preprocessor.process(document["text"])
        self.add_tokens(document_id, tokens)

    def add_tokens(self, document_id: str, tokens: Sequence[str]) -> None:
        """Add one document whose tokens were already produced by the preprocessor."""
        if not isinstance(document_id, str) or not document_id:
            raise ValueError("document_id must be a non-empty string.")
        if document_id in self._document_ids:
            raise ValueError(f"Duplicate document ID: {document_id!r}.")
        if any(not isinstance(token, str) or not token for token in tokens):
            raise ValueError("tokens must contain only non-empty strings.")

        self._document_ids.add(document_id)
        terms_in_document: set[str] = set()
        for position, term in enumerate(tokens):
            self._postings.setdefault(term, {}).setdefault(document_id, []).append(
                position
            )
            current = self._vocabulary.get(term)
            if current is None:
                self._vocabulary[term] = {"df": 1, "cf": 1}
            else:
                current["cf"] += 1
                if term not in terms_in_document:
                    current["df"] += 1
            terms_in_document.add(term)
        self._total_token_count += len(tokens)

    def clear(self) -> None:
        """Remove all postings, vocabulary metadata, and document statistics."""
        self._postings.clear()
        self._vocabulary.clear()
        self._document_ids.clear()
        self._total_token_count = 0

    def get_postings(self, term: str) -> dict[str, list[int]]:
        """Return a copy of all document positions for a normalized term."""
        normalized_term = self._preprocessor.process(term)
        if len(normalized_term) != 1:
            return {}
        postings = self._postings.get(normalized_term[0], {})
        return {
            document_id: positions.copy()
            for document_id, positions in postings.items()
        }

    def get_positions(self, term: str, document_id: str) -> list[int]:
        """Return positions for a term in one document, or an empty list."""
        normalized_term = self._preprocessor.process(term)
        if len(normalized_term) != 1:
            return []
        positions = self._postings.get(normalized_term[0], {}).get(document_id, [])
        return positions.copy()

    def get_term_frequency(self, term: str, document_id: str) -> int:
        """Return the number of occurrences of a term in one document."""
        return len(self.get_positions(term, document_id))

    def get_document_frequency(self, term: str) -> int:
        """Return the number of distinct documents containing a term."""
        statistics = self.get_term_statistics(term)
        return statistics["df"] if statistics is not None else 0

    def get_collection_frequency(self, term: str) -> int:
        """Return the total number of occurrences of a term in the collection."""
        statistics = self.get_term_statistics(term)
        return statistics["cf"] if statistics is not None else 0

    def get_term_statistics(self, term: str) -> dict[str, int] | None:
        """Return CF and DF for one term, or ``None`` for an unknown term."""
        normalized_term = self._normalize_term(term)
        if normalized_term is None:
            return None
        statistics = self._vocabulary.get(normalized_term)
        return statistics.copy() if statistics is not None else None

    def _normalize_term(self, term: str) -> str | None:
        normalized_terms = self._preprocessor.process(term)
        return normalized_terms[0] if len(normalized_terms) == 1 else None
