from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from weibo_vplus_crawler import app
from weibo_vplus_crawler.client import WeiboClient
from weibo_vplus_crawler.config import AppConfig
from weibo_vplus_crawler.errors import AuthError, DuplicatePageError
from weibo_vplus_crawler.exporters import build_output_paths
from weibo_vplus_crawler.parsing import classify_vplus_post, parse_article_html

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    path = FIXTURES_DIR / name
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return path.read_text(encoding="utf-8")


class FakeWeiboClient:
    def __init__(self, cookie: str, *, sleep_sec: float, timeout_sec: float) -> None:
        self.cookie = cookie
        self.sleep_sec = sleep_sec
        self.timeout_sec = timeout_sec
        self.pages_fetched = {}
        self.post_payload = load_fixture("post_page.json")["data"]
        self.article_payload = load_fixture("article_page.json")["data"]

    def preflight_auth_check(self, uid: str):
        self.pages_fetched["auth_check"] = 1
        return {"status": "ok", "message": "cookie_valid"}

    def fetch_status_page(self, *, uid: str, feature: int, page: int, since_id, bucket: str):
        self.pages_fetched[bucket] = self.pages_fetched.get(bucket, 0) + 1
        if feature == 0:
            if page > 1:
                return {"list": [], "since_id": None}
            return json.loads(json.dumps(self.post_payload))
        if page > 1:
            return {"list": [], "since_id": None}
        return json.loads(json.dumps(self.article_payload))

    def fetch_long_text(self, status_id: str):
        self.pages_fetched["status_details"] = self.pages_fetched.get("status_details", 0) + 1
        return {"longTextContent": "<p>长文正文</p>"}

    def fetch_article_html(self, article_url: str):
        self.pages_fetched["article_html"] = self.pages_fetched.get("article_html", 0) + 1
        return load_fixture("article.html")


@contextmanager
def chdir(path: str):
    current = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(current)


class CrawlerTests(unittest.TestCase):
    def test_auth_error_detected(self):
        payload = load_fixture("auth_error.json")
        client = WeiboClient("SUB=test", sleep_sec=0, timeout_sec=1)

        with self.assertRaises(AuthError):
            client._raise_for_api_error(payload, url="https://weibo.com/ajax", params={}, snippet=json.dumps(payload))

    def test_duplicate_page_detected(self):
        class DuplicateClient:
            def fetch_status_page(self, *, uid: str, feature: int, page: int, since_id, bucket: str):
                return {
                    "list": [
                        {"id": 1},
                        {"id": 2},
                    ],
                    "since_id": f"dup-{page}",
                }

        with self.assertRaises(DuplicatePageError):
            app.crawl_status_list(
                client=DuplicateClient(),
                uid="123",
                feature=0,
                max_pages=2,
                bucket="posts",
            )

    def test_classify_vplus_post(self):
        payload = load_fixture("post_page.json")
        matched, reason = classify_vplus_post(payload["data"]["list"][0])
        self.assertTrue(matched)
        self.assertIn("source=", reason)

    def test_parse_article_html(self):
        html = load_fixture("article.html")
        parsed = parse_article_html(html, "https://weibo.com/ttarticle/p/show?id=1")
        self.assertEqual(parsed["title"], "测试专栏标题")
        self.assertIn("第一段", parsed["content_text"])
        self.assertIn("<strong>加粗</strong>", parsed["content_html"])

    def test_manifest_contains_status_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = AppConfig(uid="123", cookie="SUB=test", out_dir=temp_dir)
            started = app.datetime(2026, 4, 17, tzinfo=app.timezone.utc)
            finished = app.datetime(2026, 4, 17, 0, 1, tzinfo=app.timezone.utc)
            paths = build_output_paths(temp_dir, config.uid, started)
            manifest = app.build_manifest(
                config=config,
                paths=paths,
                auth_check={"status": "ok", "message": "cookie_valid"},
                posts=[{"id": "1"}],
                articles=[{"article_id": "2"}],
                skipped_unknown=[{"id": "3"}],
                errors=[{"type": "x"}],
                pages_fetched={"posts": 1, "articles": 1},
                started_at=started,
                finished_at=finished,
                success=True,
            )
            self.assertEqual(manifest["auth_check"]["status"], "ok")
            self.assertEqual(manifest["posts_total"], 1)
            self.assertEqual(manifest["articles_total"], 1)
            self.assertEqual(manifest["errors_total"], 1)
            self.assertIn("pages_fetched", manifest)

    def test_run_writes_output_structure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = AppConfig(
                uid="123456",
                cookie="SUB=test",
                out_dir=temp_dir,
                sleep_sec=0,
                timeout_sec=1,
                max_post_pages=2,
                max_article_pages=2,
                save_raw=True,
                fail_on_unknown_article=False,
            )

            with mock.patch("weibo_vplus_crawler.app.WeiboClient", FakeWeiboClient):
                result = app.run(config)

            self.assertTrue(result["success"])
            output_dir = Path(result["output_dir"])
            self.assertTrue((output_dir / "posts.jsonl").exists())
            self.assertTrue((output_dir / "posts.csv").exists())
            self.assertTrue((output_dir / "articles.jsonl").exists())
            self.assertTrue((output_dir / "articles.csv").exists())
            self.assertTrue((output_dir / "skipped_unknown.jsonl").exists())
            self.assertTrue((output_dir / "errors.jsonl").exists())
            self.assertTrue((output_dir / "manifest.json").exists())

            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["posts_total"], 1)
            self.assertEqual(manifest["articles_total"], 1)
            self.assertEqual(manifest["skipped_total"], 1)
            self.assertEqual(manifest["errors_total"], 0)

    def test_main_fails_without_default_config(self):
        with tempfile.TemporaryDirectory() as temp_dir, chdir(temp_dir):
            exit_code = app.main([])
        self.assertEqual(exit_code, 2)

    def test_main_uses_default_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "uid": "123456",
                        "cookie": "SUB=test",
                        "out_dir": "output",
                        "sleep_sec": 0,
                        "timeout_sec": 1,
                        "max_post_pages": 1,
                        "max_article_pages": 1,
                        "save_raw": True,
                        "fail_on_unknown_article": False,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with chdir(temp_dir), mock.patch("weibo_vplus_crawler.app.run", return_value={"success": True, "message": "ok", "output_dir": "x"}):
                exit_code = app.main([])
            self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
