from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from apartment_agent.adapters import HipflatAdapter, PropertyHubAdapter
from apartment_agent.email_drafts import build_email_draft
from apartment_agent.matching import apply_matching
from apartment_agent.models import Listing, SearchCriteria, SearchSource
from apartment_agent.reporting import write_report
from apartment_agent.storage import ListingStore
from apartment_agent.utils import count_non_empty_fields, utc_now_iso


ADAPTERS = {
    "hipflat": HipflatAdapter(),
    "propertyhub": PropertyHubAdapter(),
}


def run_live(
    criteria: SearchCriteria,
    sources: list[SearchSource],
    db_path: str,
    output_dir: str,
    browser_capture: object | None = None,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    store = ListingStore(db_path)
    try:
        collected: list[Listing] = []
        errors: list[str] = []
        for source in sources:
            adapter = ADAPTERS.get(source.name.lower())
            if adapter is None:
                errors.append(f"No adapter registered for source `{source.name}`")
                continue
            try:
                collected.extend(adapter.collect(source, criteria, browser_capture=browser_capture))
            except Exception as exc:  # pragma: no cover - network and site behavior
                errors.append(f"{source.name} ({source.url}) failed: {exc}")

        return _finalize_run(
            started_at=started_at,
            criteria=criteria,
            listings=collected,
            store=store,
            output_dir=output_dir,
            errors=errors,
        )
    finally:
        store.close()


def run_seed(
    criteria: SearchCriteria,
    seed_payloads: list[dict[str, Any]],
    db_path: str,
    output_dir: str,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    store = ListingStore(db_path)
    try:
        listings = [Listing(**payload) for payload in seed_payloads]
        for listing in listings:
            if not listing.dedupe_key:
                listing.dedupe_key = listing.listing_id or listing.url
            if not listing.similarity_key:
                size_key = str(int(round(listing.size_sqm))) if listing.size_sqm is not None else "na"
                listing.similarity_key = f"{listing.project_name or listing.title}|{listing.bedrooms}|{size_key}|{listing.price_baht}"
        return _finalize_run(
            started_at=started_at,
            criteria=criteria,
            listings=listings,
            store=store,
            output_dir=output_dir,
            errors=[],
        )
    finally:
        store.close()


def next_run_delay_seconds(time_text: str, timezone_name: str) -> int:
    hour, minute = [int(part) for part in time_text.split(":", 1)]
    zone = ZoneInfo(timezone_name)
    now = datetime.now(zone)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return int((target - now).total_seconds())


def _finalize_run(
    started_at: str,
    criteria: SearchCriteria,
    listings: list[Listing],
    store: ListingStore,
    output_dir: str,
    errors: list[str],
) -> dict[str, Any]:
    unique = _dedupe_within_run(listings)
    alerts: list[dict[str, Any]] = []
    watch: list[dict[str, Any]] = []
    persisted_new = 0

    for listing in unique:
        apply_matching(listing, criteria)
        is_new, duplicate_of = store.upsert_listing(listing)
        listing.duplicate_of = duplicate_of
        if duplicate_of and f"Possible duplicate of {duplicate_of}" not in listing.red_flags:
            listing.red_flags.append(f"Possible duplicate of {duplicate_of}")
        if is_new:
            persisted_new += 1

        if listing.not_interested:
            continue

        if listing.fit_label in {"alert", "watch"}:
            draft = build_email_draft(listing, criteria)
            store.store_email_draft(draft)
            payload = listing.to_dict()
            payload["email_subject"] = draft.subject
            payload["email_body"] = draft.body
            if listing.fit_label == "alert":
                alerts.append(payload)
            else:
                watch.append(payload)

    run_id = datetime.now(ZoneInfo(criteria.timezone)).strftime("%Y%m%d-%H%M%S")
    report = {
        "run_id": run_id,
        "started_at": started_at,
        "criteria_timezone": criteria.timezone,
        "total_collected": len(listings),
        "total_unique": len(unique),
        "new_records": persisted_new,
        "alerts": sorted(alerts, key=lambda item: item["match_score"], reverse=True),
        "watch": sorted(watch, key=lambda item: item["match_score"], reverse=True),
        "errors": errors,
    }
    json_path, md_path = write_report(output_dir, report)
    report["json_report"] = str(json_path)
    report["markdown_report"] = str(md_path)
    return report


def _dedupe_within_run(listings: list[Listing]) -> list[Listing]:
    best_by_key: dict[str, Listing] = {}
    for listing in listings:
        key = _dedupe_bucket_key(listing)
        current = best_by_key.get(key)
        if current is None or _richness(listing) > _richness(current):
            best_by_key[key] = listing
    return list(best_by_key.values())


def _richness(listing: Listing) -> int:
    payload = listing.to_dict()
    score = count_non_empty_fields(payload)
    if listing.listing_source_status == "detail_ok":
        score += 10
    if listing.contact_phone or listing.contact_email:
        score += 5
    return score


def _dedupe_bucket_key(listing: Listing) -> str:
    if listing.similarity_key:
        return f"sim:{listing.similarity_key}"
    project = _slug_text(listing.project_name or listing.title)
    beds = str(listing.bedrooms or "na")
    size = str(int(round(listing.size_sqm))) if listing.size_sqm is not None else "na"
    price = str(int(round((listing.price_baht or 0) / 1000))) if listing.price_baht is not None else "na"
    floor = _slug_text(listing.floor)
    return f"fallback:{project}|{beds}|{size}|{price}|{floor}"


def _slug_text(value: str | None) -> str:
    source = (value or "").lower().strip()
    return "".join(character if character.isalnum() else "-" for character in source).strip("-")
