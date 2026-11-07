"""Lazy access to documents in the NLTK Reuters corpus."""

from collections.abc import Iterator
from typing import Protocol


class ReutersCorpus(Protocol):
    """Subset of the NLTK corpus reader interface used by the loader."""

    def fileids(self) -> list[str]: ...

    def raw(self, fileid: str) -> str: ...

    def categories(self) -> list[str]: ...


class DatasetLoader:
    """Provide Reuters metadata and lazily loaded document text."""

    def __init__(self, corpus: ReutersCorpus | None = None) -> None:
        if corpus is None:
            from nltk.corpus import reuters

            corpus = reuters
        self._corpus = corpus

    @property
    def document_count(self) -> int:
        """Return the number of Reuters documents."""
        return len(self._corpus.fileids())

    @property
    def categories(self) -> list[str]:
        """Return the Reuters category names."""
        return self._corpus.categories()

    def iter_documents(self) -> Iterator[dict[str, str]]:
        """Yield each original Reuters file ID and its raw text, one at a time."""
        for fileid in self._corpus.fileids():
            yield self.get_document(fileid)

    def get_document(self, document_id: str) -> dict[str, str]:
        """Retrieve one article by its original Reuters file ID."""
        return {
            "document_id": document_id,
            "text": self._corpus.raw(document_id),
        }
