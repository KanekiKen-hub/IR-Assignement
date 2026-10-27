"""In-memory inverted index built from preprocessed documents."""

from collections.abc import Iterable, Mapping

from src.preprocessor import Preprocessor


class InvertedIndex:
    """Map each normalized term to the set of Reuters document IDs containing it."""

    def __init__(self, preprocessor: Preprocessor | None = None) -> None:
        self._preprocessor = preprocessor or Preprocessor()
        self._postings: dict[str, set[str]] = {}
        self._document_ids: set[str] = set()

    @property
    def document_count(self) -> int:
        """Return the number of unique document IDs processed."""
        return len(self._document_ids)

    @property
    def unique_term_count(self) -> int:
        """Return the number of distinct terms in the index."""
        return len(self._postings)

    def build(self, documents: Iterable[Mapping[str, str]]) -> None:
        """Build the index from documents with ``document_id`` and raw ``text`` fields.

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
        for term in set(tokens):
            self._postings.setdefault(term, set()).add(document_id)

    def get_postings(self, term: str) -> set[str]:
        """Return document IDs containing a term, or an empty set if it is unknown."""
        normalized_term = self._preprocessor.process(term)
        if len(normalized_term) != 1:
            return set()
        return self._postings.get(normalized_term[0], set()).copy()

    def get_document_frequency(self, term: str) -> int:
        """Return the number of indexed documents containing a term."""
        return len(self.get_postings(term))
