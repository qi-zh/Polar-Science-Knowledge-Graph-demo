from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_TIMEOUT_SECONDS = 30
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}
DEFAULT_HEADERS = {
    "User-Agent": "kg-public-demo/0.1 (+https://penguin.nipr.ac.jp/)",
}


def _build_url(url: str, params: dict[str, str] | None = None) -> str:
    if not params:
        return url
    return f"{url}?{urlencode(params)}"


def fetch_json(
    url: str,
    params: dict[str, str] | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_attempts: int = 5,
) -> Any:
    request = Request(_build_url(url, params), headers=DEFAULT_HEADERS)
    for attempt in range(1, max_attempts + 1):
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code not in RETRYABLE_HTTP_CODES or attempt == max_attempts:
                raise
            time.sleep(min(2**attempt, 10))
        except URLError:
            if attempt == max_attempts:
                raise
            time.sleep(min(2**attempt, 10))
    raise RuntimeError("Unreachable retry branch in fetch_json")


def fetch_text(
    url: str,
    params: dict[str, str] | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_attempts: int = 5,
) -> str:
    request = Request(_build_url(url, params), headers=DEFAULT_HEADERS)
    for attempt in range(1, max_attempts + 1):
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return response.read().decode("utf-8")
        except HTTPError as exc:
            if exc.code not in RETRYABLE_HTTP_CODES or attempt == max_attempts:
                raise
            time.sleep(min(2**attempt, 10))
        except URLError:
            if attempt == max_attempts:
                raise
            time.sleep(min(2**attempt, 10))
    raise RuntimeError("Unreachable retry branch in fetch_text")
