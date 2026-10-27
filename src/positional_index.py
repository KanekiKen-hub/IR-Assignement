"""In-memory positional index built from preprocessed documents."""

from collections.abc import Iterable, Mapping

from src.preprocessor import Preprocessor


class PositionalIndex:
    """Map terms to document IDs and zero-based token positions."""

    def __init__(self, preprocessor: Preprocessor | None = None) -> None:
        self._preprocessor = preprocessor or Preprocessor()
        self._postings: dict[str, dict[str, list[int]]] = {}
        self._document_ids: set[str] = set()

    @property
    def document_count(self) -> int:
        """Return the number of unique document IDs processed."""
        return len(self._document_ids)

    @property
    def unique_term_count(self) -> int:
        """Return the number of distinct terms in the index."""
        return len(self._postings)

    @property
    def total_term_occurrences(self) -> int:
        """Return the total number of indexed token occurrences."""
        return sum(
            len(positions)
            for postings in self._postings.values()
            for positions in postings.values()
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
        self._postings.clear()
        self._document_ids.clear()

        for document in documents:
            self.add_document(document)

    def add_document(self, document: Mapping[str, str]) -> None:
        """Add one document to the current index."""
        document_id = document["document_id"]
        tokens = self._preprocessor.process(document["text"])
        self._document_ids.add(document_id)
        for position, term in enumerate(tokens):
            self._postings.setdefault(term, {}).setdefault(document_id, []).append(
                position
            )

    def get_postings(self, term: str) -> dict[str, list[int]]:
        """Return a copy of all document positions for a normalized term."""
        normalized_term = self._preprocessor.process(term)
        if len(normalized_term) != 1:
            return {}
        postings = self._postings.get(normalized_term[0], {})
        return {document_id: positions.copy() for document_id, positions in postings.items()}

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
