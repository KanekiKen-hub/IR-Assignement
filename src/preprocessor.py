"""Unicode-aware tokenization and Telugu text normalization."""

import unicodedata
from collections.abc import Iterable


class Preprocessor:
    """Normalize text to NFC and return an ordered sequence of tokens.

    Unicode letters and numbers are retained, including mixed tokens.
    Combining marks remain attached to their preceding token. Punctuation,
    underscores, and whitespace are separators. Stop words are retained unless
    a stop-word collection is explicitly provided.
    """

    def __init__(
        self,
        stop_words: Iterable[str] | None = None,
    ) -> None:
        self._stop_words = (
            {
                unicodedata.normalize("NFC", word).lower()
                for word in stop_words
            }
            if stop_words is not None
            else set()
        )

    def process(self, text: str) -> list[str]:
        """Return NFC-normalized lowercase tokens in source order."""
        normalized_text = unicodedata.normalize("NFC", text).lower()
        tokens: list[str] = []
        token: list[str] = []

        for character in normalized_text:
            category = unicodedata.category(character)
            if category[0] in {"L", "N"}:
                token.append(character)
            elif category[0] == "M" and token:
                token.append(character)
            elif token:
                tokens.append("".join(token))
                token.clear()

        if token:
            tokens.append("".join(token))

        if self._stop_words:
            tokens = [token for token in tokens if token not in self._stop_words]
        return tokens
