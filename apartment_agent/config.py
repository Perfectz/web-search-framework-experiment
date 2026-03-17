from __future__ import annotations

import json
from pathlib import Path

from apartment_agent.models import SearchCriteria, SearchSource


def _read_json(path: str | Path) -> dict | list:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_criteria(path: str | Path) -> SearchCriteria:
    payload = _read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Criteria file must contain an object: {path}")
    return SearchCriteria(**payload)


def load_sources(path: str | Path) -> list[SearchSource]:
    payload = _read_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Source file must contain a list: {path}")
    return [SearchSource(**item) for item in payload if item.get("enabled", True)]


def load_seed_listings(path: str | Path) -> list[dict]:
    payload = _read_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Seed file must contain a list: {path}")
    return payload

