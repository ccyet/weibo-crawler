import argparse
import csv
import json
import os
import time
from typing import Dict, Iterable, List, Optional

import requests
from tqdm import tqdm

BASE = "https://weibo.com"
AJAX = f"{BASE}/ajax"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://weibo.com/",
}


def build_session(cookie: Optional[str]) -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    if cookie:
        session.headers["Cookie"] = cookie
    return session


def request_json(
    session: requests.Session,
    url: str,
    params: Dict,
    sleep_sec: float,
    timeout: float,
    retries: int = 5,
) -> Dict:
    for i in range(retries):
        try:
            resp = session.get(url, params=params, timeout=timeout)
            if resp.status_code == 200:
                time.sleep(sleep_sec)
                return resp.json()
            time.sleep(min(2 + i, 5))
        except Exception:
            time.sleep(min(2 + i, 5))
    return {}


def fetch_mymblog_list(
    session: requests.Session,
    uid: str,
    feature: int,
    max_pages: int,
    sleep_sec: float,
    timeout: float,
) -> List[Dict]:
    results: List[Dict] = []
    since_id = None

    for page in range(1, max_pages + 1):
        params = {
            "uid": uid,
            "page": page,
            "feature": feature,
        }
        if since_id:
            params["since_id"] = since_id

        data = request_json(
            session=session,
            url=f"{AJAX}/statuses/mymblog",
            params=params,
            sleep_sec=sleep_sec,
            timeout=timeout,
        )
        if not data or "data" not in data:
            break

        items = data["data"].get("list", [])
        if not items:
            break

        results.extend(items)
        since_id = data["data"].get("since_id")

    return results


def fetch_long_text(
    session: requests.Session,
    status_id: str,
    sleep_sec: float,
    timeout: float,
) -> str:
    data = request_json(
        session=session,
        url=f"{AJAX}/statuses/show",
        params={"id": status_id, "isGetLongText": "true"},
        sleep_sec=sleep_sec,
        timeout=timeout,
    )
    return data.get("data", {}).get("longTextContent", "")


def enrich_long_text(
    session: requests.Session,
    items: List[Dict],
    sleep_sec: float,
    timeout: float,
) -> List[Dict]:
    for item in tqdm(items, desc="expand long text"):
        if item.get("isLongText"):
            item["longTextContent"] = fetch_long_text(
                session=session,
                status_id=str(item.get("id", "")),
                sleep_sec=sleep_sec,
                timeout=timeout,
            )
    return items


def flatten_for_csv(item: Dict) -> Dict:
    flat = {}
    for k, v in item.items():
        if isinstance(v, (dict, list)):
            flat[k] = json.dumps(v, ensure_ascii=False)
        else:
            flat[k] = v
    return flat


def write_jsonl(path: str, rows: Iterable[Dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: str, rows: List[Dict]) -> None:
    if not rows:
        return

    normalized = [flatten_for_csv(r) for r in rows]
    fieldnames = sorted({key for row in normalized for key in row.keys()})

    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(normalized)


def save_manifest(path: str, uid: str, posts_count: int, articles_count: int) -> None:
    manifest = {
        "uid": uid,
        "posts_count": posts_count,
        "articles_count": articles_count,
        "generated_at": int(time.time()),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl Weibo posts and articles by UID.")
    parser.add_argument("--uid", required=True, help="Weibo UID")
    parser.add_argument("--cookie", default="", help="Weibo cookie string")
    parser.add_argument("--max-post-pages", type=int, default=10, help="Max pages for normal posts")
    parser.add_argument("--max-article-pages", type=int, default=10, help="Max pages for articles")
    parser.add_argument("--out", default="./output", help="Output directory")
    parser.add_argument("--sleep", type=float, default=1.0, help="Sleep seconds between requests")
    parser.add_argument("--timeout", type=float, default=20.0, help="Request timeout")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    session = build_session(args.cookie)

    posts = fetch_mymblog_list(
        session=session,
        uid=args.uid,
        feature=0,
        max_pages=args.max_post_pages,
        sleep_sec=args.sleep,
        timeout=args.timeout,
    )
    posts = enrich_long_text(
        session=session,
        items=posts,
        sleep_sec=args.sleep,
        timeout=args.timeout,
    )

    articles = fetch_mymblog_list(
        session=session,
        uid=args.uid,
        feature=10,
        max_pages=args.max_article_pages,
        sleep_sec=args.sleep,
        timeout=args.timeout,
    )
    articles = enrich_long_text(
        session=session,
        items=articles,
        sleep_sec=args.sleep,
        timeout=args.timeout,
    )

    write_jsonl(os.path.join(args.out, "posts.jsonl"), posts)
    write_jsonl(os.path.join(args.out, "articles.jsonl"), articles)
    write_csv(os.path.join(args.out, "posts.csv"), posts)
    write_csv(os.path.join(args.out, "articles.csv"), articles)
    save_manifest(
        os.path.join(args.out, "manifest.json"),
        uid=args.uid,
        posts_count=len(posts),
        articles_count=len(articles),
    )

    print(f"Done. posts={len(posts)}, articles={len(articles)}, out={args.out}")


if __name__ == "__main__":
    main()
