"""Deterministic tokenization and optional text normalization."""

import re
from collections.abc import Iterable


_TOKEN_PATTERN = re.compile(r"[^\W_]+", flags=re.UNICODE)


class Preprocessor:
    """Normalize text into an ordered sequence of tokens.

    Letters and digits are retained, including mixed alphanumeric tokens.
    Punctuation and underscores are token separators. Stop words are retained
    unless a stop-word collection is explicitly provided. Porter stemming is
    also opt-in.
    """

    def __init__(
        self,
        stop_words: Iterable[str] | None = None,
        stemming: bool = False,
    ) -> None:
        self._stop_words = (
            {word.lower() for word in stop_words} if stop_words is not None else set()
        )
        self._stemmer = None
        if stemming:
            from nltk.stem import PorterStemmer

            self._stemmer = PorterStemmer()

    def process(self, text: str) -> list[str]:
        """Return lowercase tokens in source order, applying configured options."""
        tokens = _TOKEN_PATTERN.findall(text.lower())
        if self._stop_words:
            tokens = [token for token in tokens if token not in self._stop_words]
        if self._stemmer is not None:
            tokens = [self._stemmer.stem(token) for token in tokens]
        return tokens
