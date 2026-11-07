from src.preprocessor import Preprocessor


def test_lowercases_tokenizes_and_removes_punctuation():
    processor = Preprocessor()

    assert processor.process("The company reported higher oil prices.") == [
        "the",
        "company",
        "reported",
        "higher",
        "oil",
        "prices",
    ]


def test_preserves_numbers_and_mixed_alphanumeric_tokens():
    processor = Preprocessor()

    assert processor.process("Oil rose 12.5% in 1987; plan B-52.") == [
        "oil",
        "rose",
        "12",
        "5",
        "in",
        "1987",
        "plan",
        "b",
        "52",
    ]


def test_empty_document_produces_no_tokens():
    assert Preprocessor().process("") == []


def test_telugu_unicode_tokens_and_repeated_terms_are_preserved():
    assert Preprocessor().process("తెలుగు భాష తెలుగు") == [
        "తెలుగు",
        "భాష",
        "తెలుగు",
    ]


def test_telugu_combining_marks_remain_attached_to_the_token():
    assert Preprocessor().process("కా\u0c02 తెలుగు") == ["కాం", "తెలుగు"]


def test_normalizes_decomposed_input_to_nfc():
    import unicodedata

    text = "క\u0c46\u0c56"

    tokens = Preprocessor().process(text)

    assert tokens == [unicodedata.normalize("NFC", text)]
    assert all(unicodedata.is_normalized("NFC", token) for token in tokens)


def test_punctuation_and_whitespace_separate_telugu_tokens():
    assert Preprocessor().process("తెలుగు,\tభాష!\nతెలుగు") == [
        "తెలుగు",
        "భాష",
        "తెలుగు",
    ]


def test_stop_word_removal_is_opt_in():
    assert Preprocessor().process("The oil price") == ["the", "oil", "price"]
    assert Preprocessor(stop_words={"the"}).process("The oil price") == [
        "oil",
        "price",
    ]


def test_stop_words_are_normalized_using_the_same_nfc_rule():
    assert Preprocessor(stop_words={"క\u0c46\u0c56"}).process("క\u0c48") == []
