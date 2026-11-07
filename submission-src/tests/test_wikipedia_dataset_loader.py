import bz2

import pytest

from src.wikipedia_dataset_loader import WikipediaDatasetLoader


_XML_PREFIX = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/">'
)
_XML_SUFFIX = "</mediawiki>"


def _page(
    page_id,
    title,
    text,
    *,
    namespace="0",
    redirect=None,
    revision_id="900",
):
    redirect_tag = (
        f'<redirect title="{redirect}" />' if redirect is not None else ""
    )
    text_tag = "" if text is None else f"<text>{text}</text>"
    return (
        "<page>"
        f"<title>{title}</title>"
        f"<ns>{namespace}</ns>"
        f"<id>{page_id}</id>"
        f"{redirect_tag}"
        "<revision>"
        f"<id>{revision_id}</id>"
        f"{text_tag}"
        "</revision>"
        "</page>"
    )


def _write_dump(path, pages):
    xml = _XML_PREFIX + "".join(pages) + _XML_SUFFIX
    with bz2.open(path, "wt", encoding="utf-8") as dump:
        dump.write(xml)


def test_reads_compressed_xml_and_extracts_page_id_title_and_telugu_text(tmp_path):
    dump_path = tmp_path / "synthetic.xml.bz2"
    text = "తెలుగు భాష తెలుగు"
    _write_dump(dump_path, [_page("17", "తెలుగు", text, revision_id="880")])

    loader = WikipediaDatasetLoader(dump_path)

    assert list(loader.iter_documents()) == [
        {
            "document_id": "17",
            "page_id": "17",
            "title": "తెలుగు",
            "text": text,
        }
    ]
    assert loader.pages_encountered == 1
    assert loader.articles_processed == 1
    assert loader.articles_skipped == 0


def test_filters_non_main_pages_redirects_and_empty_articles(tmp_path):
    dump_path = tmp_path / "synthetic.xml.bz2"
    _write_dump(
        dump_path,
        [
            _page("1", "Wikipedia:Help", "help text", namespace="4"),
            _page("2", "Redirect", "#REDIRECT [[తెలుగు]]", redirect="తెలుగు"),
            _page("3", "Empty", "  \n\t"),
            _page("4", "Valid", "తెలుగు"),
        ],
    )

    loader = WikipediaDatasetLoader(dump_path, max_articles=None)

    assert [doc["document_id"] for doc in loader.iter_documents()] == ["4"]
    assert loader.pages_encountered == 4
    assert loader.articles_processed == 1
    assert loader.skipped_by_reason == {
        "non_main_namespace": 1,
        "redirect": 1,
        "empty_text": 1,
    }


def test_article_limit_counts_valid_articles_not_skipped_pages(tmp_path):
    dump_path = tmp_path / "synthetic.xml.bz2"
    _write_dump(
        dump_path,
        [
            _page("1", "Talk", "talk", namespace="1"),
            _page("2", "Redirect", "redirect", redirect="Valid"),
            _page("3", "First", "first"),
            _page("4", "Second", "second"),
            _page("5", "NotRead", "not read"),
        ],
    )

    loader = WikipediaDatasetLoader(dump_path, max_articles=2)

    assert [doc["document_id"] for doc in loader.iter_documents()] == ["3", "4"]
    assert loader.pages_encountered == 4
    assert loader.articles_processed == 2
    assert loader.articles_skipped == 2


def test_unlimited_mode_yields_every_usable_article(tmp_path):
    dump_path = tmp_path / "synthetic.xml.bz2"
    _write_dump(
        dump_path,
        [_page(str(page_id), f"Page {page_id}", "content") for page_id in range(3)],
    )

    loader = WikipediaDatasetLoader(dump_path, max_articles=None)

    assert [doc["page_id"] for doc in loader.iter_documents()] == ["0", "1", "2"]


def test_iteration_is_lazy_until_documents_are_requested(tmp_path):
    dump_path = tmp_path / "synthetic.xml.bz2"
    _write_dump(
        dump_path,
        [_page(str(page_id), f"Page {page_id}", "content") for page_id in range(3)],
    )
    loader = WikipediaDatasetLoader(dump_path, max_articles=1)

    documents = loader.iter_documents()

    assert loader.pages_encountered == 0
    assert next(documents)["document_id"] == "0"
    assert loader.pages_encountered == 1
    assert loader.articles_processed == 1
    assert next(documents, None) is None
    assert loader.pages_encountered == 1


@pytest.mark.parametrize("limit", [0, -1, True])
def test_rejects_non_positive_or_boolean_article_limits(tmp_path, limit):
    with pytest.raises(ValueError, match="positive integer or None"):
        WikipediaDatasetLoader(tmp_path / "missing.xml.bz2", max_articles=limit)


def test_rejects_non_mediawiki_xml(tmp_path):
    dump_path = tmp_path / "not_mediawiki.xml.bz2"
    with bz2.open(dump_path, "wt", encoding="utf-8") as dump:
        dump.write("<root />")

    with pytest.raises(ValueError, match="not a supported MediaWiki export"):
        list(WikipediaDatasetLoader(dump_path).iter_documents())


def test_rejects_missing_page_metadata(tmp_path):
    dump_path = tmp_path / "missing_metadata.xml.bz2"
    _write_dump(
        dump_path,
        [
            "<page><title>Missing ID</title><ns>0</ns>"
            "<revision><text>usable</text></revision></page>"
        ],
    )
    loader = WikipediaDatasetLoader(dump_path, max_articles=None)

    assert list(loader.iter_documents()) == []
    assert loader.skipped_by_reason == {"missing_page_metadata": 1}
