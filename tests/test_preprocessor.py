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


def test_stop_word_removal_is_opt_in():
    assert Preprocessor().process("The oil price") == ["the", "oil", "price"]
    assert Preprocessor(stop_words={"the"}).process("The oil price") == [
        "oil",
        "price",
    ]


def test_stemming_is_opt_in():
    assert Preprocessor().process("companies reported") == ["companies", "reported"]
    assert Preprocessor(stemming=True).process("companies reported") == [
        "compani",
        "report",
    ]
