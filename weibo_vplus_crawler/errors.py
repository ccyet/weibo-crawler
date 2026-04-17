from __future__ import annotations

from typing import Any, Dict, Optional


class CrawlerError(Exception):
    code = "crawler_error"

    def __init__(self, message: str, *, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigError(CrawlerError):
    code = "config_error"


class AuthError(CrawlerError):
    code = "auth_error"


class RateLimitError(CrawlerError):
    code = "rate_limit_error"


class WeiboResponseError(CrawlerError):
    code = "weibo_response_error"


class DuplicatePageError(CrawlerError):
    code = "duplicate_page_error"


class ArticleParseError(CrawlerError):
    code = "article_parse_error"


class NoAccessibleContentError(CrawlerError):
    code = "no_accessible_content"
