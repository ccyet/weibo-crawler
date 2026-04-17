from __future__ import annotations

import sys
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .client import WeiboClient
from .config import AppConfig, load_app_config
from .errors import (
    ArticleParseError,
    AuthError,
    ConfigError,
    CrawlerError,
    DuplicatePageError,
    NoAccessibleContentError,
    WeiboResponseError,
)
from .exporters import OutputPaths, build_output_paths, write_csv, write_json, write_jsonl
from .html_utils import html_to_text
from .parsing import (
    build_permalink,
    classify_vplus_post,
    extract_article_url,
    extract_text_excerpt,
    parse_article_html,
    parse_article_id,
)

VERSION = "1.0.0"


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        config = load_app_config(argv)
    except ConfigError as exc:
        print(f"[ERROR] {exc.message}", file=sys.stderr)
        return 2

    result = run(config)
    status = "SUCCESS" if result["success"] else "FAILED"
    print(f"{status}: {result['message']}")
    print(f"OUTPUT_DIR={result['output_dir']}")
    return 0 if result["success"] else 1


def run(config: AppConfig) -> Dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    paths = build_output_paths(config.out_dir, config.uid, started_at)
    client = WeiboClient(
        config.cookie,
        sleep_sec=config.sleep_sec,
        timeout_sec=config.timeout_sec,
    )

    posts: List[Dict[str, Any]] = []
    articles: List[Dict[str, Any]] = []
    skipped_unknown: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    auth_check: Dict[str, Any] = {"status": "pending", "message": ""}
    success = False
    message = ""

    try:
        auth_check = client.preflight_auth_check(config.uid)

        post_items = crawl_status_list(
            client=client,
            uid=config.uid,
            feature=0,
            max_pages=config.max_post_pages,
            bucket="posts",
        )
        article_items = crawl_status_list(
            client=client,
            uid=config.uid,
            feature=10,
            max_pages=config.max_article_pages,
            bucket="articles",
        )

        posts, skipped_posts = collect_vplus_posts(client, post_items, config)
        skipped_unknown.extend(skipped_posts)

        articles, skipped_articles, article_errors = collect_articles(client, article_items, config)
        skipped_unknown.extend(skipped_articles)
        errors.extend(article_errors)

        if not posts and not articles:
            raise NoAccessibleContentError(
                "未抓到任何可访问的 V+ 发帖或专栏文章",
                details={"uid": config.uid},
            )

        success = True
        message = f"posts={len(posts)}, articles={len(articles)}, skipped={len(skipped_unknown)}"
    except CrawlerError as exc:
        auth_check = build_failed_auth_check(auth_check, exc)
        errors.append(error_record(exc, stage="run", fatal=True))
        message = exc.message

    finished_at = datetime.now(timezone.utc)
    manifest = build_manifest(
        config=config,
        paths=paths,
        auth_check=auth_check,
        posts=posts,
        articles=articles,
        skipped_unknown=skipped_unknown,
        errors=errors,
        pages_fetched=dict(client.pages_fetched),
        started_at=started_at,
        finished_at=finished_at,
        success=success,
    )

    persist_outputs(paths, posts, articles, skipped_unknown, errors, manifest)
    return {
        "success": success,
        "message": message,
        "output_dir": paths.root_dir,
    }


def crawl_status_list(
    *,
    client: WeiboClient,
    uid: str,
    feature: int,
    max_pages: int,
    bucket: str,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_since_ids: set[str] = set()
    previous_signature: Optional[Tuple[str, ...]] = None
    since_id: Optional[str] = None

    for page in range(1, max_pages + 1):
        payload = client.fetch_status_page(
            uid=uid,
            feature=feature,
            page=page,
            since_id=since_id,
            bucket=bucket,
        )
        items = payload.get("list")
        if not isinstance(items, list):
            raise WeiboResponseError(
                "微博列表响应缺少 list",
                details={"feature": feature, "page": page},
            )
        if not items:
            break

        signature = tuple(str(item.get("id") or "") for item in items)
        if signature and signature == previous_signature:
            raise DuplicatePageError(
                "微博列表返回了重复页面",
                details={"feature": feature, "page": page, "signature": signature},
            )
        previous_signature = signature

        added = 0
        for item in items:
            item_id = str(item.get("id") or "")
            if not item_id:
                continue
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            results.append(item)
            added += 1

        if added == 0:
            raise DuplicatePageError(
                "当前页全部都是重复微博",
                details={"feature": feature, "page": page},
            )

        next_since_id = payload.get("since_id")
        if next_since_id not in (None, ""):
            next_since_id = str(next_since_id)
            if next_since_id in seen_since_ids:
                raise DuplicatePageError(
                    "since_id 重复，分页可能陷入循环",
                    details={"feature": feature, "page": page, "since_id": next_since_id},
                )
            seen_since_ids.add(next_since_id)
        since_id = next_since_id

    return results


def collect_vplus_posts(
    client: WeiboClient,
    items: Iterable[Dict[str, Any]],
    config: AppConfig,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    posts: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for item in items:
        matched, reason = classify_vplus_post(item)
        if not matched:
            skipped.append(build_skipped_record(item, category="post", reason=reason, save_raw=config.save_raw))
            continue

        detail_payload: Dict[str, Any] = {}
        long_text_html = ""
        long_text_text = ""
        if item.get("isLongText"):
            detail_payload = client.fetch_long_text(str(item.get("id")))
            long_text_html = str(detail_payload.get("longTextContent") or "")
            long_text_text = html_to_text(long_text_html)

        record = {
            "id": str(item.get("id") or ""),
            "mblogid": item.get("mblogid"),
            "created_at": item.get("created_at"),
            "permalink": build_permalink(item),
            "text_raw": item.get("text_raw"),
            "source": item.get("source"),
            "reposts_count": item.get("reposts_count"),
            "comments_count": item.get("comments_count"),
            "attitudes_count": item.get("attitudes_count"),
            "pic_num": item.get("pic_num"),
            "pics": item.get("pics"),
            "page_info": item.get("page_info"),
            "is_long_text": bool(item.get("isLongText")),
            "long_text_html": long_text_html,
            "long_text_text": long_text_text,
            "vplus_reason": reason,
        }
        if config.save_raw:
            record["raw_status"] = deepcopy(item)
            record["raw_status_detail"] = deepcopy(detail_payload) if detail_payload else None
        posts.append(record)

    return posts, skipped


def collect_articles(
    client: WeiboClient,
    items: Iterable[Dict[str, Any]],
    config: AppConfig,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    articles: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    seen_article_ids: set[str] = set()

    for item in items:
        article_url = extract_article_url(item)
        if not article_url:
            skipped_record = build_skipped_record(
                item,
                category="article",
                reason="article_url_not_found",
                save_raw=config.save_raw,
            )
            if config.fail_on_unknown_article:
                raise ArticleParseError(
                    "文章候选项缺少可解析的文章链接",
                    details={"status_id": item.get("id")},
                )
            skipped.append(skipped_record)
            continue

        article_id = parse_article_id(article_url)
        if not article_id:
            skipped_record = build_skipped_record(
                item,
                category="article",
                reason="article_id_not_found",
                save_raw=config.save_raw,
            )
            if config.fail_on_unknown_article:
                raise ArticleParseError(
                    "文章链接里没有找到文章 ID",
                    details={"article_url": article_url},
                )
            skipped.append(skipped_record)
            continue

        if article_id in seen_article_ids:
            continue
        seen_article_ids.add(article_id)

        try:
            page_html = client.fetch_article_html(article_url)
            parsed = parse_article_html(page_html, article_url)
        except CrawlerError as exc:
            if config.fail_on_unknown_article:
                raise
            errors.append(error_record(exc, stage="article_fetch", fatal=False))
            continue

        record = {
            "article_id": article_id,
            "article_url": article_url,
            "title": parsed["title"],
            "content_html": parsed["content_html"],
            "content_text": parsed["content_text"],
            "status_id": str(item.get("id") or ""),
            "status_mblogid": item.get("mblogid"),
            "status_created_at": item.get("created_at"),
            "status_text_raw": item.get("text_raw"),
            "status_permalink": build_permalink(item),
        }
        if config.save_raw:
            record["raw_status"] = deepcopy(item)
            record["raw_article_html"] = page_html
        articles.append(record)

    return articles, skipped, errors


def build_skipped_record(
    item: Dict[str, Any],
    *,
    category: str,
    reason: str,
    save_raw: bool,
) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "category": category,
        "id": str(item.get("id") or ""),
        "mblogid": item.get("mblogid"),
        "reason": reason,
        "excerpt": extract_text_excerpt(item),
    }
    article_url = extract_article_url(item)
    if article_url:
        record["article_url"] = article_url
    if save_raw:
        record["raw_item"] = deepcopy(item)
    return record


def error_record(exc: CrawlerError, *, stage: str, fatal: bool) -> Dict[str, Any]:
    return {
        "type": exc.code,
        "stage": stage,
        "fatal": fatal,
        "message": exc.message,
        "details": deepcopy(exc.details),
    }


def build_manifest(
    *,
    config: AppConfig,
    paths: OutputPaths,
    auth_check: Dict[str, Any],
    posts: List[Dict[str, Any]],
    articles: List[Dict[str, Any]],
    skipped_unknown: List[Dict[str, Any]],
    errors: List[Dict[str, Any]],
    pages_fetched: Dict[str, int],
    started_at: datetime,
    finished_at: datetime,
    success: bool,
) -> Dict[str, Any]:
    return {
        "version": VERSION,
        "success": success,
        "uid": config.uid,
        "output_dir": paths.root_dir,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "auth_check": auth_check,
        "posts_total": len(posts),
        "articles_total": len(articles),
        "skipped_total": len(skipped_unknown),
        "errors_total": len(errors),
        "pages_fetched": pages_fetched,
        "config": config.to_manifest_dict(),
    }


def persist_outputs(
    paths: OutputPaths,
    posts: List[Dict[str, Any]],
    articles: List[Dict[str, Any]],
    skipped_unknown: List[Dict[str, Any]],
    errors: List[Dict[str, Any]],
    manifest: Dict[str, Any],
) -> None:
    write_jsonl(paths.posts_jsonl, posts)
    write_jsonl(paths.articles_jsonl, articles)
    write_jsonl(paths.skipped_unknown_jsonl, skipped_unknown)
    write_jsonl(paths.errors_jsonl, errors)
    write_csv(paths.posts_csv, posts)
    write_csv(paths.articles_csv, articles)
    write_json(paths.manifest_json, manifest)


def build_failed_auth_check(current: Dict[str, Any], exc: CrawlerError) -> Dict[str, Any]:
    if current.get("status") == "ok":
        return current
    status = "failed"
    if isinstance(exc, AuthError):
        status = "auth_failed"
    return {
        "status": status,
        "message": exc.message,
        "error_type": exc.code,
    }
