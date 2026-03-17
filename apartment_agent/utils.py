from __future__ import annotations

import html
import json
import re
import time
from http.client import IncompleteRead
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/134.0.0.0 Safari/537.36"
)

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fetch_html(url: str, timeout: int = 25, attempts: int = 3) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8", "ignore")
        except (IncompleteRead, OSError) as exc:
            last_error = exc
            if attempt == attempts:
                break
            time.sleep(0.75 * attempt)
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def load_next_data(html_text: str) -> dict[str, Any]:
    match = NEXT_DATA_RE.search(html_text)
    if not match:
        raise ValueError("Could not find __NEXT_DATA__ payload")
    return json.loads(match.group(1))


def normalize_whitespace(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def clean_html_fragment(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return normalize_whitespace(text)


def set_query_param(url: str, key: str, value: str | int) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query[key] = str(value)
    return urlunparse(parsed._replace(query=urlencode(query)))


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    query = [(k, v) for k, v in parse_qsl(parsed.query) if not k.lower().startswith("utm_")]
    cleaned = parsed._replace(query=urlencode(query), fragment="")
    normalized = urlunparse(cleaned).rstrip("/")
    return normalized


def slug_text(value: str | None) -> str:
    cleaned = normalize_whitespace(value).lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned)
    return cleaned.strip("-")


def extract_size_sqm_from_text(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m2|m²)", text, re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1))


def extract_bedrooms_from_text(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"(\d+)\s*(?:bed|bedroom)", text, re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def extract_transit_mentions(text: str | None) -> str | None:
    if not text:
        return None
    matches = re.findall(r"\b(?:BTS|MRT)\s+[A-Za-z][A-Za-z0-9 \-]+", text)
    if not matches:
        return None
    deduped: list[str] = []
    seen: set[str] = set()
    for item in matches:
        normalized = normalize_whitespace(item)
        lowered = normalized.lower()
        if lowered not in seen:
            deduped.append(normalized)
            seen.add(lowered)
    return ", ".join(deduped)


def truthy_labels(flags: dict[str, Any] | None, label_map: dict[str, str]) -> list[str]:
    if not flags:
        return []
    return [label for key, label in label_map.items() if flags.get(key) is True]


def count_non_empty_fields(payload: dict[str, Any]) -> int:
    count = 0
    for value in payload.values():
        if value in (None, "", [], {}, False):
            continue
        count += 1
    return count


def ensure_parent(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target
