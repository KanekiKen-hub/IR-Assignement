"""Streaming access to main-namespace pages in a compressed Wikipedia dump."""

import bz2
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path


_EXPORT_NAMESPACE = "http://www.mediawiki.org/xml/export-0.11/"
_MEDIAWIKI_TAG = f"{{{_EXPORT_NAMESPACE}}}mediawiki"
_PAGE_TAG = f"{{{_EXPORT_NAMESPACE}}}page"


class WikipediaDatasetLoader:
    """Yield usable main-namespace Wikipedia pages from a bzip2 XML dump.

    The page limit applies to yielded, non-redirect articles with non-empty
    text. The yielded text is the raw wikitext stored in the XML dump.
    """

    def __init__(
        self,
        dump_path: str | Path,
        max_articles: int | None = 5000,
    ) -> None:
        if max_articles is not None and (
            isinstance(max_articles, bool)
            or not isinstance(max_articles, int)
            or max_articles < 1
        ):
            raise ValueError("max_articles must be a positive integer or None.")

        self.dump_path = Path(dump_path)
        self.max_articles = max_articles
        self.pages_encountered = 0
        self.articles_processed = 0
        self._skipped_by_reason: dict[str, int] = {}

    @property
    def articles_skipped(self) -> int:
        """Return the number of skipped pages encountered in the last iteration."""
        return sum(self._skipped_by_reason.values())

    @property
    def skipped_by_reason(self) -> dict[str, int]:
        """Return a copy of the skipped-page counts grouped by reason."""
        return self._skipped_by_reason.copy()

    def iter_documents(self) -> Iterator[dict[str, str]]:
        """Yield page IDs, titles, and raw text without retaining the dump in RAM."""
        self.pages_encountered = 0
        self.articles_processed = 0
        self._skipped_by_reason.clear()

        with bz2.open(self.dump_path, "rb") as source:
            context = ET.iterparse(source, events=("start", "end"))
            try:
                _, root = next(context)
            except StopIteration:
                raise ValueError("The Wikipedia XML dump is empty.") from None

            if root.tag != _MEDIAWIKI_TAG:
                raise ValueError(
                    "The XML root is not a supported MediaWiki export "
                    f"(found {root.tag!r})."
                )

            for event, page in context:
                if event != "end" or page.tag != _PAGE_TAG:
                    continue

                self.pages_encountered += 1
                document, skip_reason = self._extract_document(page)
                root.clear()

                if skip_reason is not None:
                    self._skipped_by_reason[skip_reason] = (
                        self._skipped_by_reason.get(skip_reason, 0) + 1
                    )
                    continue

                self.articles_processed += 1
                yield document

                if (
                    self.max_articles is not None
                    and self.articles_processed >= self.max_articles
                ):
                    return

    @staticmethod
    def _extract_document(
        page: ET.Element,
    ) -> tuple[dict[str, str] | None, str | None]:
        title_element = page.find(f"{{{_EXPORT_NAMESPACE}}}title")
        namespace_element = page.find(f"{{{_EXPORT_NAMESPACE}}}ns")
        page_id_element = page.find(f"{{{_EXPORT_NAMESPACE}}}id")

        if namespace_element is None or namespace_element.text != "0":
            return None, "non_main_namespace"

        if page.find(f"{{{_EXPORT_NAMESPACE}}}redirect") is not None:
            return None, "redirect"

        if (
            title_element is None
            or not title_element.text
            or page_id_element is None
            or not page_id_element.text
        ):
            return None, "missing_page_metadata"

        text_element = page.find(
            f"{{{_EXPORT_NAMESPACE}}}revision/{{{_EXPORT_NAMESPACE}}}text"
        )
        text = text_element.text if text_element is not None else None
        if text is None or not text.strip():
            return None, "empty_text"

        page_id = page_id_element.text
        return (
            {
                "document_id": page_id,
                "page_id": page_id,
                "title": title_element.text,
                "text": text,
            },
            None,
        )
