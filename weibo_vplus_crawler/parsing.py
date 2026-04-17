from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, Iterator, Optional, Tuple

from .errors import ArticleParseError
from .html_utils import extract_node_inner_html, extract_node_text, html_to_text

ARTICLE_URL_RE = re.compile(
    r"(?:https?:)?//(?:www\.)?weibo\.com/ttarticle/p/show\?id=(?P<id>\d+)",
    re.IGNORECASE,
)
ALT_ARTICLE_URL_RE = re.compile(
    r"(?:https?:)?//card\.weibo\.com/article/m/show/id/(?P<id>\d+)",
    re.IGNORECASE,
)
STRONG_VPLUS_MARKERS = (
    "粉丝订阅",
    "粉丝订阅vplus",
    "v+会员",
    "vplus",
    "真爱粉",
    "付费可见",
    "付费订阅",
    "会员专属",
    "专属内容",
)


def classify_vplus_post(item: Dict[str, Any]) -> Tuple[bool, str]:
    visible = item.get("visible")
    if isinstance(visible, dict):
        for key in ("type", "pay_type", "list_id", "is_paid", "paid"):
            value = visible.get(key)
            if value not in (None, "", 0, "0", False):
                return True, f"visible.{key}={value}"
        matched = _match_keywords_in_values(visible.values())
        if matched:
            return True, f"visible.keyword={matched}"

    for key in ("pay_info", "membership_info", "content_auth_info", "paid_info"):
        value = item.get(key)
        if isinstance(value, dict) and value:
            return True, f"{key}.present"

    for key in ("mblog_vip_type", "mblogtype", "readtimetype", "paid", "is_paid"):
        value = item.get(key)
        if value not in (None, "", 0, "0", False):
            return True, f"{key}={value}"

    source = _normalize_string(item.get("source"))
    if source:
        matched = _find_marker(source)
        if matched:
            return True, f"source={matched}"

    title = item.get("title")
    if isinstance(title, dict):
        matched = _match_keywords_in_values(title.values())
        if matched:
            return True, f"title.keyword={matched}"
    elif isinstance(title, str):
        matched = _find_marker(title)
        if matched:
            return True, f"title={matched}"

    for key in ("screen_name_suffix_new", "tag_struct"):
        matched = _find_marker(_collect_marker_text(item.get(key)))
        if matched:
            return True, f"{key}={matched}"

    return False, "no_explicit_vplus_marker"


def extract_article_url(item: Dict[str, Any]) -> Optional[str]:
    for value in _iter_strings(item):
        url = _normalize_article_url(value)
        if url:
            return url
    return None


def parse_article_html(page_html: str, article_url: str) -> Dict[str, str]:
    title = extract_node_text(page_html, "articleTitle")
    body_html = extract_node_inner_html(page_html, "contentBody")
    if not title:
        raise ArticleParseError("文章标题解析失败", details={"article_url": article_url})
    if not body_html:
        raise ArticleParseError("文章正文解析失败", details={"article_url": article_url})

    return {
        "title": title,
        "content_html": body_html,
        "content_text": html_to_text(body_html),
    }


def build_permalink(item: Dict[str, Any]) -> Optional[str]:
    user = item.get("user") or {}
    uid = user.get("idstr") or user.get("id")
    mblogid = item.get("mblogid")
    if not uid or not mblogid:
        return None
    return f"https://weibo.com/{uid}/{mblogid}"


def extract_text_excerpt(item: Dict[str, Any], limit: int = 120) -> str:
    text = html_to_text(str(item.get("text_raw") or item.get("text") or ""))
    if not text:
        text = _normalize_string(item.get("source")) or str(item.get("id") or "")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def parse_article_id(article_url: str) -> Optional[str]:
    match = ARTICLE_URL_RE.search(article_url)
    if match:
        return match.group("id")
    match = ALT_ARTICLE_URL_RE.search(article_url)
    if match:
        return match.group("id")
    return None


def to_json_blob(data: Any) -> Optional[str]:
    if data is None:
        return None
    return json.dumps(data, ensure_ascii=False)


def _normalize_article_url(value: str) -> Optional[str]:
    match = ARTICLE_URL_RE.search(value)
    if match:
        return f"https://weibo.com/ttarticle/p/show?id={match.group('id')}"
    match = ALT_ARTICLE_URL_RE.search(value)
    if match:
        return f"https://weibo.com/ttarticle/p/show?id={match.group('id')}"
    return None


def _iter_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for nested in value.values():
            yield from _iter_strings(nested)
        return
    if isinstance(value, list):
        for nested in value:
            yield from _iter_strings(nested)


def _collect_marker_text(value: Any) -> str:
    return " ".join(_iter_strings(value))


def _normalize_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _match_keywords_in_values(values: Iterable[Any]) -> Optional[str]:
    for value in values:
        matched = _find_marker(_normalize_string(value))
        if matched:
            return matched
    return None


def _find_marker(text: str) -> Optional[str]:
    normalized = _normalize_string(text).lower()
    if not normalized:
        return None
    for marker in STRONG_VPLUS_MARKERS:
        if marker in normalized:
            return marker
    return None
