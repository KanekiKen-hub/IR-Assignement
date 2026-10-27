from src.inverted_index import InvertedIndex


def test_builds_postings_and_document_frequencies():
    index = InvertedIndex()
    documents = [
        {"document_id": "doc-1", "text": "Oil prices rose."},
        {"document_id": "doc-2", "text": "Oil prices fell."},
        {"document_id": "doc-3", "text": "Prices stabilized."},
    ]

    index.build(documents)

    assert index.document_count == 3
    assert index.unique_term_count == 5
    assert index.get_postings("oil") == {"doc-1", "doc-2"}
    assert index.get_postings("prices") == {"doc-1", "doc-2", "doc-3"}
    assert index.get_document_frequency("oil") == 2
    assert index.get_document_frequency("prices") == 3


def test_repeated_terms_do_not_duplicate_document_ids():
    index = InvertedIndex()
    index.build([{"document_id": "doc-1", "text": "oil oil oil"}])

    assert index.get_postings("oil") == {"doc-1"}
    assert index.get_document_frequency("oil") == 1


def test_unknown_or_non_single_token_terms_have_empty_postings():
    index = InvertedIndex()
    index.build([{"document_id": "doc-1", "text": "oil prices"}])

    assert index.get_postings("unknown") == set()
    assert index.get_document_frequency("unknown") == 0
    assert index.get_postings("oil prices") == set()


def test_empty_document_is_counted_without_adding_terms():
    index = InvertedIndex()
    index.build([{"document_id": "empty", "text": ""}])

    assert index.document_count == 1
    assert index.unique_term_count == 0


def test_rebuilding_replaces_previous_index():
    index = InvertedIndex()
    index.build([{"document_id": "old", "text": "oil"}])
    index.build([{"document_id": "new", "text": "gold"}])

    assert index.document_count == 1
    assert index.get_postings("oil") == set()
    assert index.get_postings("gold") == {"new"}
