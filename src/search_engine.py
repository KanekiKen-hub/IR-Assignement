"""Boolean and phrase retrieval over the project indexes."""

import re

from src.inverted_index import InvertedIndex
from src.positional_index import PositionalIndex


_BOOLEAN_OPERATOR = re.compile(r"\b(AND|OR)\b", flags=re.IGNORECASE)


class SearchEngine:
    """Search indexed documents using terms, Boolean operators, or phrases."""

    def __init__(
        self,
        inverted_index: InvertedIndex,
        positional_index: PositionalIndex,
    ) -> None:
        self._inverted_index = inverted_index
        self._positional_index = positional_index
        self._preprocessor = positional_index.preprocessor

    def search(self, query: str) -> set[str]:
        """Return matching document IDs; malformed non-empty queries raise ValueError.

        Supported syntax is a single term, a quoted phrase, or exactly two
        single terms separated by AND or OR. Empty queries return no results.
        """
        query = query.strip()
        if not query:
            return set()

        if '"' in query:
            if not (query.startswith('"') and query.endswith('"')) or query.count('"') != 2:
                raise ValueError("Malformed phrase query: use one pair of double quotes.")
            phrase = query[1:-1]
            if not self._preprocessor.process(phrase):
                raise ValueError("Malformed phrase query: the phrase must contain a token.")
            return set(self.phrase_positions(phrase))

        operators = list(_BOOLEAN_OPERATOR.finditer(query))
        if operators:
            if len(operators) != 1:
                raise ValueError("Malformed Boolean query: use exactly one AND or OR.")
            operator = operators[0]
            left = self._single_term(query[: operator.start()])
            right = self._single_term(query[operator.end() :])
            left_postings = self._inverted_index.get_postings(left)
            right_postings = self._inverted_index.get_postings(right)
            if operator.group().upper() == "AND":
                return left_postings & right_postings
            return left_postings | right_postings

        term = self._single_term(query)
        return self._inverted_index.get_postings(term)

    def phrase_positions(self, phrase: str) -> dict[str, list[int]]:
        """Return zero-based starting positions for each exact phrase match."""
        terms = self._preprocessor.process(phrase)
        if not terms:
            return {}

        term_postings = [self._positional_index.get_postings(term) for term in terms]
        candidate_documents = set(term_postings[0])
        for postings in term_postings[1:]:
            candidate_documents.intersection_update(postings)
            if not candidate_documents:
                return {}

        matches: dict[str, list[int]] = {}
        for document_id in candidate_documents:
            starts = set(term_postings[0][document_id])
            for offset, postings in enumerate(term_postings[1:], start=1):
                positions = set(postings[document_id])
                starts = {start for start in starts if start + offset in positions}
                if not starts:
                    break
            if starts:
                matches[document_id] = sorted(starts)
        return matches

    def _single_term(self, query_part: str) -> str:
        terms = self._preprocessor.process(query_part.strip())
        if len(terms) != 1:
            raise ValueError("Each term query and Boolean operand must contain one token.")
        return terms[0]
