from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Optional


NODE_START_RE = re.compile(
    r"<(?P<tag>[a-zA-Z0-9]+)\b[^>]*\bnode-type=[\"'](?P<name>[^\"']+)[\"'][^>]*>",
    re.IGNORECASE,
)


class _TextExtractor(HTMLParser):
    BLOCK_TAGS = {
        "p",
        "div",
        "br",
        "li",
        "ul",
        "ol",
        "figure",
        "figcaption",
        "section",
        "article",
        "h1",
        "h2",
        "h3",
        "h4",
        "blockquote",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "br":
            self.parts.append("\n")
        elif tag in self.BLOCK_TAGS:
            self._append_newline()

    def handle_endtag(self, tag: str) -> None:
        if tag in self.BLOCK_TAGS:
            self._append_newline()

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def _append_newline(self) -> None:
        if not self.parts:
            return
        if self.parts[-1] != "\n":
            self.parts.append("\n")

    def get_text(self) -> str:
        text = "".join(self.parts)
        lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line)


def html_to_text(raw_html: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(raw_html or "")
    return html.unescape(extractor.get_text())


def extract_node_inner_html(page_html: str, node_type: str) -> Optional[str]:
    for match in NODE_START_RE.finditer(page_html):
        if match.group("name") != node_type:
            continue
        tag_name = match.group("tag").lower()
        return _extract_balanced_inner_html(page_html, tag_name, match.end())
    return None


def extract_node_text(page_html: str, node_type: str) -> Optional[str]:
    inner_html = extract_node_inner_html(page_html, node_type)
    if inner_html is None:
        return None
    return html_to_text(inner_html)


def _extract_balanced_inner_html(page_html: str, tag_name: str, start_pos: int) -> Optional[str]:
    tag_pattern = re.compile(rf"</?{re.escape(tag_name)}\b[^>]*>", re.IGNORECASE)
    depth = 1
    current = start_pos

    while depth > 0:
        match = tag_pattern.search(page_html, current)
        if match is None:
            return None

        token = match.group(0)
        if token.startswith("</"):
            depth -= 1
        elif not token.endswith("/>"):
            depth += 1

        if depth == 0:
            return page_html[start_pos:match.start()]
        current = match.end()

    return None
