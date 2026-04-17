from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

from .errors import AuthError, RateLimitError, WeiboResponseError

BASE = "https://weibo.com"
AJAX = f"{BASE}/ajax"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://weibo.com/",
}


class WeiboClient:
    def __init__(self, cookie: str, *, sleep_sec: float, timeout_sec: float) -> None:
        self.sleep_sec = sleep_sec
        self.timeout_sec = timeout_sec
        self.pages_fetched: Dict[str, int] = defaultdict(int)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.headers["Cookie"] = cookie

    def preflight_auth_check(self, uid: str) -> Dict[str, Any]:
        payload = self.fetch_status_page(uid=uid, feature=0, page=1, since_id=None, bucket="auth_check")
        items = payload.get("list")
        if not isinstance(items, list):
            raise WeiboResponseError(
                "鉴权预检失败：响应缺少 data.list",
                details={"uid": uid, "feature": 0},
            )
        return {
            "status": "ok",
            "message": "cookie_valid",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def fetch_status_page(
        self,
        *,
        uid: str,
        feature: int,
        page: int,
        since_id: Optional[str],
        bucket: str,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"uid": uid, "page": page, "feature": feature}
        if since_id:
            params["since_id"] = since_id

        data = self.get_json(f"{AJAX}/statuses/mymblog", params=params)
        payload = data.get("data")
        if not isinstance(payload, dict):
            raise WeiboResponseError(
                "微博列表响应缺少 data",
                details={"url": f"{AJAX}/statuses/mymblog", "params": params},
            )
        self.pages_fetched[bucket] += 1
        return payload

    def fetch_long_text(self, status_id: str) -> Dict[str, Any]:
        data = self.get_json(
            f"{AJAX}/statuses/show",
            params={"id": status_id, "isGetLongText": "true"},
        )
        payload = data.get("data")
        if not isinstance(payload, dict):
            raise WeiboResponseError(
                "微博详情响应缺少 data",
                details={"status_id": status_id},
            )
        self.pages_fetched["status_details"] += 1
        return payload

    def fetch_article_html(self, article_url: str) -> str:
        response = self._request("GET", article_url)
        if "login.php" in response.url:
            raise AuthError("抓取文章时跳转到登录页", details={"article_url": article_url})
        self.pages_fetched["article_html"] += 1
        return response.text

    def get_json(self, url: str, *, params: Dict[str, Any]) -> Dict[str, Any]:
        response = self._request("GET", url, params=params)
        snippet = response.text[:500]
        try:
            data = response.json()
        except ValueError as exc:
            raise WeiboResponseError(
                "响应不是合法 JSON",
                details={"url": url, "params": params, "snippet": snippet},
            ) from exc

        self._raise_for_api_error(data, url=url, params=params, snippet=snippet)
        return data

    def _request(self, method: str, url: str, *, params: Optional[Dict[str, Any]] = None) -> requests.Response:
        try:
            response = self.session.request(method, url, params=params, timeout=self.timeout_sec)
        except requests.RequestException as exc:
            raise WeiboResponseError(
                "请求微博接口失败",
                details={"url": url, "params": params or {}, "error": repr(exc)},
            ) from exc

        if response.status_code in (403, 418, 429):
            raise RateLimitError(
                "请求过于频繁或被微博限流",
                details={"url": url, "params": params or {}, "status_code": response.status_code},
            )
        if response.status_code != 200:
            raise WeiboResponseError(
                "微博接口返回非 200 状态码",
                details={
                    "url": url,
                    "params": params or {},
                    "status_code": response.status_code,
                    "snippet": response.text[:500],
                },
            )

        if self.sleep_sec > 0:
            time.sleep(self.sleep_sec)
        return response

    def _raise_for_api_error(self, data: Dict[str, Any], *, url: str, params: Dict[str, Any], snippet: str) -> None:
        redirect_url = str(data.get("url") or "")
        if data.get("ok") == -100 or "login.php" in redirect_url:
            raise AuthError(
                "Cookie 失效或未登录",
                details={"url": url, "params": params, "snippet": snippet},
            )

        text = " ".join(
            str(value)
            for value in (
                data.get("msg"),
                data.get("errmsg"),
                data.get("message"),
                snippet,
            )
            if value
        ).lower()
        if any(token in text for token in ("频繁", "rate", "too many", "访问过于频繁")):
            raise RateLimitError(
                "请求过于频繁或被微博限流",
                details={"url": url, "params": params, "snippet": snippet},
            )
