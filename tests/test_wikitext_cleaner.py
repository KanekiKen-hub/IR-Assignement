import unicodedata

from src.preprocessor import Preprocessor
from src.positional_index import PositionalIndex
from src.wikitext_cleaner import WikipediaTextCleaner


def test_plain_telugu_text_is_preserved_and_normalized():
    assert WikipediaTextCleaner().clean("తెలుగు భాష ఒక సంపద.") == (
        "తెలుగు భాష ఒక సంపద."
    )


def test_internal_links_keep_visible_telugu_text():
    cleaner = WikipediaTextCleaner()

    assert cleaner.clean("[[తెలుగు భాష]]") == "తెలుగు భాష"
    assert cleaner.clean("[[భారతదేశం|భారతదేశం]]") == "భారతదేశం"
    assert cleaner.clean("[[:en:NASA]]") == "NASA"


def test_nested_templates_preserve_selected_readable_description():
    source = "{{Infobox |description={{small|తెలుగు భాష}}|image=Map.svg}}"

    assert WikipediaTextCleaner().clean(source) == "తెలుగు భాష"


def test_reference_tags_are_removed_in_paired_and_self_closing_forms():
    source = "తెలుగు<ref>citation text</ref> భాష<ref name=\"source\" />."

    assert WikipediaTextCleaner().clean(source) == "తెలుగు భాష."


def test_external_links_keep_labels_and_discard_urls():
    source = "చూడండి [https://example.org తెలుగు లింకు] https://example.net/page"

    assert WikipediaTextCleaner().clean(source) == "చూడండి తెలుగు లింకు"


def test_headings_and_bold_italic_formatting_keep_words():
    source = "== తెలుగు శీర్షిక ==\n'''ముఖ్యం''' మరియు ''విశేషం''"

    assert WikipediaTextCleaner().clean(source) == (
        "తెలుగు శీర్షిక ముఖ్యం మరియు విశేషం"
    )


def test_category_declarations_are_removed():
    source = "వ్యాసం [[Category:తెలుగు]] [[వర్గం:భారతదేశం|అ]]"

    assert WikipediaTextCleaner().clean(source) == "వ్యాసం"


def test_file_markup_is_removed_but_readable_caption_is_kept():
    cleaner = WikipediaTextCleaner()

    assert cleaner.clean("[[File:map.png|thumb|తెలుగు పటం]]") == "తెలుగు పటం"
    assert cleaner.clean("[[దస్త్రం:map.png|కుడి|250px|తెలుగు పటం]]") == "తెలుగు పటం"
    assert cleaner.clean("[[బొమ్మ:map.png|thumbnail|right|250px|తెలుగు పటం]]") == (
        "తెలుగు పటం"
    )
    assert cleaner.clean("[[Image:map.png|thumb]]") == ""


def test_tables_keep_cell_content_and_remove_table_formatting():
    source = (
        '{| class="wikitable"\n'
        '! పేరు !! రాజధాని\n'
        '|-\n'
        '| ఆంధ్రప్రదేశ్ || అమరావతి\n'
        '|}'
    )

    assert WikipediaTextCleaner().clean(source) == "పేరు రాజధాని ఆంధ్రప్రదేశ్ అమరావతి"


def test_html_tags_keep_readable_text_and_remove_irrelevant_reference_content():
    source = "<div>తెలుగు <b>భాష</b><br/>వ్యాసం</div><script>noise</script>"

    assert WikipediaTextCleaner().clean(source) == "తెలుగు భాష వ్యాసం"


def test_html_entities_are_decoded_without_losing_telugu():
    assert WikipediaTextCleaner().clean("తెలుగు&nbsp;&amp;&nbsp;భాష") == (
        "తెలుగు & భాష"
    )


def test_telugu_unicode_and_nfc_are_preserved():
    source = "క\u0c46\u0c56 భాష"
    cleaned = WikipediaTextCleaner().clean(source)

    assert cleaned == unicodedata.normalize("NFC", source)
    assert all(unicodedata.is_normalized("NFC", token) for token in cleaned.split())


def test_punctuation_whitespace_and_list_content_are_readable():
    source = "తెలుగు,\tభాష!\n* మొదటి అంశం\n# రెండవ అంశం"

    assert WikipediaTextCleaner().clean(source) == (
        "తెలుగు, భాష! మొదటి అంశం రెండవ అంశం"
    )


def test_mediawiki_magic_words_are_removed():
    assert WikipediaTextCleaner().clean("వ్యాసం __NOTOC__ __NOEDITSECTION__") == (
        "వ్యాసం"
    )


def test_unparsed_nested_links_and_html_tags_are_recovered():
    source = "తెలుగు <center>[[లక్ష్యం|చదవగల పాఠ్యం</center>]]"

    assert WikipediaTextCleaner().clean(source) == "తెలుగు చదవగల పాఠ్యం"


def test_empty_article_produces_empty_text_and_no_tokens():
    cleaner = WikipediaTextCleaner()
    text = cleaner.clean("")

    assert text == ""
    assert Preprocessor().process(text) == []


def test_mixed_telugu_and_english_text_is_retained():
    source = "తెలుగు Wikipedia వ్యాసం"
    cleaned = WikipediaTextCleaner().clean(source)

    assert cleaned == source
    assert Preprocessor().process(cleaned) == ["తెలుగు", "wikipedia", "వ్యాసం"]


def test_article_wikitext_flows_through_existing_preprocessor_and_index():
    cleaner = WikipediaTextCleaner()
    processor = Preprocessor()
    raw_text = "'''తెలుగు''' [[భాష]] తెలుగు"
    clean_text = cleaner.clean(raw_text)
    tokens = processor.process(clean_text)
    index = PositionalIndex(processor)
    index.add_document({"document_id": "42", "text": clean_text})

    assert tokens == ["తెలుగు", "భాష", "తెలుగు"]
    assert index.get_positions("తెలుగు", "42") == [0, 2]
    assert index.get_positions("భాష", "42") == [1]


def test_content_templates_retain_readable_text_without_template_syntax():
    source = "{{quote|తెలుగు మాటలు}}"

    assert WikipediaTextCleaner().clean(source) == "తెలుగు మాటలు"
    assert "{{" not in WikipediaTextCleaner().clean(source)
