import pytest

from src.index_builder import build_positional_index
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


def test_telugu_single_document_positions_and_collection_statistics():
    processor = Preprocessor()
    tokens = processor.process("తెలుగు భాష తెలుగు")
    index = PositionalIndex(processor)
    index.add_tokens("786", tokens)

    assert index.get_positions("తెలుగు", "786") == [0, 2]
    assert index.get_positions("భాష", "786") == [1]
    assert index.get_document_frequency("తెలుగు") == 1
    assert index.get_collection_frequency("తెలుగు") == 2
    assert index.get_document_frequency("భాష") == 1
    assert index.get_collection_frequency("భాష") == 1


def test_cf_counts_occurrences_and_df_counts_distinct_documents():
    index = build_positional_index(
        [
            ("DOC1", ["తెలుగు", "తెలుగు", "భాష"]),
            ("DOC2", ["తెలుగు", "భాష", "భాష"]),
        ]
    )

    assert index.get_term_statistics("తెలుగు") == {"df": 2, "cf": 3}
    assert index.get_term_statistics("భాష") == {"df": 2, "cf": 3}
    assert index.get_positions("తెలుగు", "DOC1") == [0, 1]
    assert index.get_positions("తెలుగు", "DOC2") == [0]
    assert index.get_positions("భాష", "DOC1") == [2]
    assert index.get_positions("భాష", "DOC2") == [1, 2]


def test_repeated_occurrences_in_one_document_increase_cf_not_df():
    index = build_positional_index(
        [("DOC1", ["తెలుగు", "తెలుగు", "తెలుగు", "భాష"])]
    )

    assert index.get_collection_frequency("తెలుగు") == 3
    assert index.get_document_frequency("తెలుగు") == 1
    assert index.get_positions("తెలుగు", "DOC1") == [0, 1, 2]


def test_empty_documents_count_as_documents_but_add_no_tokens():
    index = build_positional_index([("empty", []), ("DOC1", ["తెలుగు"])])

    assert index.document_count == 2
    assert index.total_token_count == 1
    assert index.total_term_occurrences == 1
    assert index.unique_term_count == 1
    assert index.vocabulary["తెలుగు"] == {"df": 1, "cf": 1}


def test_statistics_match_preprocessed_normalized_token_sequence():
    processor = Preprocessor()
    tokens = processor.process("క\u0c46\u0c56 తెలుగు తెలుగు")
    index = PositionalIndex(processor)
    index.add_tokens("page-1", tokens)

    assert tokens == ["క\u0c48", "తెలుగు", "తెలుగు"]
    assert index.total_token_count == len(tokens)
    assert index.total_term_occurrences == len(tokens)
    assert index.get_positions("క\u0c48", "page-1") == [0]
    assert index.get_positions("తెలుగు", "page-1") == [1, 2]
    assert index.get_collection_frequency("తెలుగు") == 2


def test_unknown_term_statistics_are_clear_and_zero_valued():
    index = PositionalIndex()

    assert index.get_term_statistics("తెలుగు") is None
    assert index.get_collection_frequency("తెలుగు") == 0
    assert index.get_document_frequency("తెలుగు") == 0
    assert index.get_postings("తెలుగు") == {}


def test_vocabulary_metadata_is_separate_and_read_only():
    index = build_positional_index([("DOC1", ["తెలుగు", "భాష"])])

    with pytest.raises(TypeError):
        index.vocabulary["కొత్త"] = {"df": 1, "cf": 1}
    with pytest.raises(TypeError):
        index.vocabulary["తెలుగు"]["cf"] = 20

    assert index.vocabulary == {
        "తెలుగు": {"df": 1, "cf": 1},
        "భాష": {"df": 1, "cf": 1},
    }
    assert "DOC1" not in index.vocabulary


def test_duplicate_document_ids_are_rejected_without_merging_positions():
    index = PositionalIndex()
    index.add_tokens("DOC1", ["తెలుగు"])

    with pytest.raises(ValueError, match="Duplicate document ID"):
        index.add_tokens("DOC1", ["భాష"])

    assert index.get_positions("తెలుగు", "DOC1") == [0]
    assert index.get_positions("భాష", "DOC1") == []


def test_document_and_collection_statistics_are_reset_on_rebuild():
    index = PositionalIndex()
    index.build([{"document_id": "old", "text": "తెలుగు తెలుగు"}])
    index.build([{"document_id": "new", "text": "భాష"}])

    assert index.document_count == 1
    assert index.total_token_count == 1
    assert index.get_collection_frequency("తెలుగు") == 0
    assert index.get_document_frequency("తెలుగు") == 0
    assert index.get_collection_frequency("భాష") == 1


def test_invalid_processed_tokens_are_rejected_without_partial_update():
    index = PositionalIndex()

    with pytest.raises(ValueError, match="non-empty strings"):
        index.add_tokens("DOC1", ["తెలుగు", ""])

    assert index.document_count == 0
    assert index.total_token_count == 0
    assert index.unique_term_count == 0
