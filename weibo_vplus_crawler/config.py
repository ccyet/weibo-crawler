from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from .errors import ConfigError

DEFAULT_CONFIG_NAME = "config.json"


@dataclass
class AppConfig:
    uid: str
    cookie: str
    out_dir: str = "output"
    sleep_sec: float = 1.0
    timeout_sec: float = 20.0
    max_post_pages: int = 10
    max_article_pages: int = 10
    save_raw: bool = True
    fail_on_unknown_article: bool = False
    config_path: Optional[str] = None

    def to_manifest_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data.pop("cookie", None)
        return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crawl Weibo V+ posts and column articles.")
    parser.add_argument("--config", help="Path to config.json")
    parser.add_argument("--uid", help="Weibo UID")
    parser.add_argument("--cookie", help="Weibo cookie string")
    parser.add_argument("--out", "--out-dir", dest="out_dir", help="Base output directory")
    parser.add_argument("--sleep", dest="sleep_sec", type=float, help="Sleep seconds between requests")
    parser.add_argument("--timeout", dest="timeout_sec", type=float, help="Request timeout seconds")
    parser.add_argument("--max-post-pages", type=int, help="Max pages for post discovery")
    parser.add_argument("--max-article-pages", type=int, help="Max pages for article discovery")
    parser.add_argument("--save-raw", dest="save_raw", action="store_true", help="Save raw response blobs")
    parser.add_argument("--no-save-raw", dest="save_raw", action="store_false", help="Do not save raw response blobs")
    parser.add_argument(
        "--fail-on-unknown-article",
        dest="fail_on_unknown_article",
        action="store_true",
        help="Abort when an article candidate cannot be resolved",
    )
    parser.add_argument(
        "--skip-unknown-article-errors",
        dest="fail_on_unknown_article",
        action="store_false",
        help="Skip unknown article candidates and continue",
    )
    parser.set_defaults(save_raw=None, fail_on_unknown_article=None)
    return parser


def load_app_config(argv: Optional[List[str]] = None, *, cwd: Optional[str] = None) -> AppConfig:
    cwd = os.path.abspath(cwd or os.getcwd())
    argv = list(argv or [])
    parser = build_parser()
    args = parser.parse_args(argv)

    default_config_path = os.path.join(cwd, DEFAULT_CONFIG_NAME)
    config_path = _resolve_config_path(args.config, cwd) if args.config else default_config_path

    file_values: Dict[str, Any] = {}
    should_load_file = False
    if args.config:
        if not os.path.exists(config_path):
            raise ConfigError(f"找不到配置文件: {config_path}", details={"config_path": config_path})
        should_load_file = True
    elif not argv:
        if not os.path.exists(config_path):
            raise ConfigError(
                f"找不到默认配置文件: {config_path}",
                details={"config_path": config_path},
            )
        should_load_file = True
    elif os.path.exists(config_path):
        should_load_file = True

    if should_load_file:
        file_values = _load_json_file(config_path)

    values: Dict[str, Any] = {
        "uid": "",
        "cookie": "",
        "out_dir": "output",
        "sleep_sec": 1.0,
        "timeout_sec": 20.0,
        "max_post_pages": 10,
        "max_article_pages": 10,
        "save_raw": True,
        "fail_on_unknown_article": False,
    }
    values.update(file_values)

    for key in (
        "uid",
        "cookie",
        "out_dir",
        "sleep_sec",
        "timeout_sec",
        "max_post_pages",
        "max_article_pages",
        "save_raw",
        "fail_on_unknown_article",
    ):
        cli_value = getattr(args, key, None)
        if cli_value is not None:
            values[key] = cli_value

    config = AppConfig(
        uid=str(values["uid"]).strip(),
        cookie=str(values["cookie"]).strip(),
        out_dir=str(values["out_dir"]).strip() or "output",
        sleep_sec=float(values["sleep_sec"]),
        timeout_sec=float(values["timeout_sec"]),
        max_post_pages=int(values["max_post_pages"]),
        max_article_pages=int(values["max_article_pages"]),
        save_raw=bool(values["save_raw"]),
        fail_on_unknown_article=bool(values["fail_on_unknown_article"]),
        config_path=config_path if should_load_file else None,
    )
    _validate_config(config)
    return config


def _resolve_config_path(path: str, cwd: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(cwd, path))


def _load_json_file(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"找不到配置文件: {path}", details={"config_path": path}) from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"配置文件不是合法 JSON: {path}",
            details={"config_path": path, "line": exc.lineno, "column": exc.colno},
        ) from exc

    if not isinstance(data, dict):
        raise ConfigError(f"配置文件必须是 JSON 对象: {path}", details={"config_path": path})
    return data


def _validate_config(config: AppConfig) -> None:
    if not config.uid:
        raise ConfigError("配置缺少 uid", details={"field": "uid"})
    if not config.cookie:
        raise ConfigError("配置缺少 cookie", details={"field": "cookie"})
    if config.sleep_sec < 0:
        raise ConfigError("sleep_sec 不能小于 0", details={"field": "sleep_sec", "value": config.sleep_sec})
    if config.timeout_sec <= 0:
        raise ConfigError("timeout_sec 必须大于 0", details={"field": "timeout_sec", "value": config.timeout_sec})
    if config.max_post_pages <= 0:
        raise ConfigError(
            "max_post_pages 必须大于 0",
            details={"field": "max_post_pages", "value": config.max_post_pages},
        )
    if config.max_article_pages <= 0:
        raise ConfigError(
            "max_article_pages 必须大于 0",
            details={"field": "max_article_pages", "value": config.max_article_pages},
        )
