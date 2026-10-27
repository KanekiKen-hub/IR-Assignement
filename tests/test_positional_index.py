from src.positional_index import PositionalIndex
from src.preprocessor import Preprocessor


def test_stores_zero_based_positions_in_processed_token_sequence():
    index = PositionalIndex()
    index.build(
        [
            {"document_id": "doc-1", "text": "Oil, oil prices."},
            {"document_id": "doc-2", "text": "Prices rose."},
        ]
    )

    assert index.get_postings("oil") == {"doc-1": [0, 1]}
    assert index.get_postings("prices") == {"doc-1": [2], "doc-2": [0]}
    assert index.get_positions("oil", "doc-1") == [0, 1]
    assert index.get_term_frequency("oil", "doc-1") == 2
    assert index.get_term_frequency("oil", "doc-2") == 0


def test_positions_follow_tokens_after_optional_stop_word_removal():
    index = PositionalIndex(Preprocessor(stop_words={"the"}))
    index.build([{"document_id": "doc-1", "text": "the oil and the prices"}])

    assert index.get_postings("oil") == {"doc-1": [0]}
    assert index.get_postings("prices") == {"doc-1": [2]}


def test_unknown_terms_and_documents_return_empty_values():
    index = PositionalIndex()
    index.build([{"document_id": "doc-1", "text": "oil prices"}])

    assert index.get_postings("unknown") == {}
    assert index.get_positions("oil", "missing") == []
    assert index.get_positions("oil prices", "doc-1") == []
    assert index.get_term_frequency("unknown", "doc-1") == 0


def test_returned_postings_are_copies():
    index = PositionalIndex()
    index.build([{"document_id": "doc-1", "text": "oil prices"}])

    postings = index.get_postings("oil")
    postings["doc-1"].append(99)
    positions = index.get_positions("prices", "doc-1")
    positions.append(99)

    assert index.get_positions("oil", "doc-1") == [0]
    assert index.get_positions("prices", "doc-1") == [1]


def test_rebuilding_replaces_previous_index():
    index = PositionalIndex()
    index.build([{"document_id": "old", "text": "oil"}])
    index.build([{"document_id": "new", "text": "gold"}])

    assert index.document_count == 1
    assert index.get_positions("oil", "old") == []
    assert index.get_positions("gold", "new") == [0]
