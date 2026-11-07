"""Convert MediaWiki wikitext into readable text for indexing."""

import html
import re
import unicodedata

import mwparserfromhell
from mwparserfromhell.nodes import (
    Comment,
    ExternalLink,
    Heading,
    HTMLEntity,
    Tag,
    Template,
    Wikilink,
)


_DISCARDED_TAGS = {
    "gallery",
    "math",
    "ref",
    "references",
    "script",
    "score",
    "style",
    "syntaxhighlight",
    "timeline",
}
_BLOCK_TAGS = {
    "blockquote",
    "br",
    "div",
    "li",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "tr",
    "ul",
}
_CONTENT_TEMPLATES = {
    "blockquote",
    "center",
    "flatlist",
    "hlist",
    "lang",
    "nowrap",
    "plainlist",
    "quote",
    "small",
    "transl",
    "ubl",
    "unbulleted list",
}
_CONTENT_TEMPLATE_FIELDS = {
    "caption",
    "content",
    "description",
    "image_caption",
    "motto",
    "native_name",
    "quote",
    "text",
    "title",
}
_TABLE_ATTRIBUTE = re.compile(
    r"^\s*(?:style|class|rowspan|colspan|scope|align|valign|width|bgcolor)\s*=.*?\|\s*",
    flags=re.IGNORECASE,
)
_FORMATTING_MARKERS = re.compile(r"'{2,5}")
_LIST_MARKERS = re.compile(r"(?m)^[ \t]*[*#;:]+[ \t]*")
_WHITESPACE = re.compile(r"\s+")
_URL = re.compile(r"https?://\S+", flags=re.IGNORECASE)
_MAGIC_WORD = re.compile(r"__[A-Z][A-Z0-9_]*__", flags=re.IGNORECASE)
_IMAGE_DIMENSION = re.compile(r"\d+(?:x\d+)?px", flags=re.IGNORECASE)
_RESIDUAL_WIKILINK = re.compile(r"\[\[([^\[\]]+)\]\]")
_HTML_TAG = re.compile(r"</?[A-Za-z][^>]*>")


class WikipediaTextCleaner:
    """Clean common MediaWiki markup while retaining readable article content.

    Templates are parsed structurally: known text wrappers and selected
    descriptive fields are retained, while layout and metadata templates are
    omitted. Internal links retain their visible text, and reference content,
    categories, and non-text media markup are discarded.
    """

    def clean(self, text: str) -> str:
        """Return NFC-normalized readable text from raw article wikitext."""
        text = self._clean_tables(text)
        code = mwparserfromhell.parse(text)
        rendered = self._render_code(code)
        rendered = html.unescape(rendered)
        rendered = self._recover_residual_markup(rendered)
        rendered = _URL.sub(" ", rendered)
        rendered = _MAGIC_WORD.sub(" ", rendered)
        rendered = unicodedata.normalize("NFC", rendered)
        return _WHITESPACE.sub(" ", rendered).strip()

    def _render_code(self, code: mwparserfromhell.wikicode.Wikicode) -> str:
        output: list[str] = []
        for node in code.nodes:
            if isinstance(node, Comment):
                continue
            if isinstance(node, Template):
                output.append(self._render_template(node))
            elif isinstance(node, Wikilink):
                output.append(self._render_wikilink(node))
            elif isinstance(node, ExternalLink):
                if node.title is not None:
                    output.append(self._render_code(node.title))
            elif isinstance(node, Tag):
                tag_name = str(node.tag).strip().lower()
                if tag_name in _DISCARDED_TAGS:
                    continue
                contents = (
                    self._render_code(node.contents)
                    if node.contents is not None
                    else ""
                )
                if tag_name in _BLOCK_TAGS:
                    output.extend((" ", contents, " "))
                else:
                    output.append(contents)
            elif isinstance(node, Heading):
                output.extend((" ", self._render_code(node.title), " "))
            elif isinstance(node, HTMLEntity):
                output.append(html.unescape(str(node)))
            else:
                output.append(self._render_text(str(node)))
        return "".join(output)

    def _render_template(self, template: Template) -> str:
        name = template.name.strip_code().strip().casefold()
        name = re.sub(r"^(?:subst|safesubst):", "", name)
        if name in _CONTENT_TEMPLATES:
            values = [str(parameter.value) for parameter in template.params]
            if name == "lang":
                values = values[1:2]
            return self._render_code(mwparserfromhell.parse(" ".join(values)))

        selected_values = [
            str(parameter.value)
            for parameter in template.params
            if parameter.showkey
            and parameter.name.strip_code().strip().casefold()
            in _CONTENT_TEMPLATE_FIELDS
        ]
        if not selected_values:
            return ""
        return self._render_code(
            mwparserfromhell.parse(" ".join(selected_values))
        )

    def _render_wikilink(self, link: Wikilink) -> str:
        target = str(link.title).strip()
        visible_title = target.lstrip()
        leading_colon = visible_title.startswith(":")
        if leading_colon:
            visible_title = visible_title[1:]
        namespace, separator, _ = visible_title.partition(":")
        namespace = namespace.casefold()
        if not leading_colon and namespace in {"category", "వర్గం"}:
            return ""
        if not leading_colon and namespace in {"file", "image", "దస్త్రం", "బొమ్మ"}:
            return self._render_file_caption(link.text)
        if link.text is not None:
            content = link.text
        elif leading_colon and re.match(r"^:[a-z][a-z0-9-]{1,14}:", target):
            content = target.split(":", 2)[2]
        else:
            content = link.title
        return self._render_code(
            mwparserfromhell.parse(str(content).split("#", 1)[0])
        )

    def _recover_residual_markup(self, text: str) -> str:
        def replace_link(match: re.Match[str]) -> str:
            target_and_text = match.group(1).split("|", 1)
            target = target_and_text[0].strip()
            display = target_and_text[1] if len(target_and_text) == 2 else target
            namespace = target.lstrip(":").partition(":")[0].casefold()
            leading_colon = target.startswith(":")
            if not leading_colon and namespace in {"category", "వర్గం"}:
                return ""
            if not leading_colon and namespace in {
                "file",
                "image",
                "దస్త్రం",
                "బొమ్మ",
            }:
                return self._render_file_caption(mwparserfromhell.parse(display))
            return self._render_code(mwparserfromhell.parse(display))

        for _ in range(5):
            recovered = _RESIDUAL_WIKILINK.sub(replace_link, text)
            if recovered == text:
                break
            text = recovered
        text = text.replace("[[", " ").replace("]]", " ")
        text = _HTML_TAG.sub(" ", text)
        return _FORMATTING_MARKERS.sub("", text)

    def _render_file_caption(self, text: mwparserfromhell.wikicode.Wikicode | None) -> str:
        if text is None:
            return ""
        options = {
            "center",
            "frameless",
            "frame",
            "left",
            "right",
            "thumb",
            "thumbnail",
            "ఎడమ",
            "కుడి",
        }
        captions: list[str] = []
        for part in str(text).split("|"):
            part = _TABLE_ATTRIBUTE.sub("", part).strip()
            if (
                not part
                or part.casefold() in options
                or _IMAGE_DIMENSION.fullmatch(part)
            ):
                continue
            if "=" in part:
                key, value = part.split("=", 1)
                if key.strip().casefold() not in {"alt", "caption"}:
                    continue
                part = value
            captions.append(self._render_code(mwparserfromhell.parse(part)))
        return " ".join(captions)

    @staticmethod
    def _render_text(text: str) -> str:
        text = _FORMATTING_MARKERS.sub("", text)
        text = _LIST_MARKERS.sub("", text)
        return text

    @staticmethod
    def _clean_tables(text: str) -> str:
        output: list[str] = []
        table_depth = 0

        for line in text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("{|"):
                table_depth += 1
                continue
            if table_depth and stripped.startswith("|}"):
                table_depth -= 1
                continue
            if not table_depth:
                output.append(line)
                continue
            if stripped.startswith("|-"):
                continue
            if stripped.startswith("|+"):
                output.append(stripped[2:].strip())
                continue
            if stripped.startswith(("|", "!")):
                marker = stripped[0]
                separator = "!!" if marker == "!" else "||"
                cells = stripped[1:].split(separator)
                for cell in cells:
                    cell = _TABLE_ATTRIBUTE.sub("", cell).strip()
                    if cell:
                        output.append(cell)
        return "\n".join(output)
