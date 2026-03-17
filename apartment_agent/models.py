from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class SearchCriteria:
    max_rent_baht: int | None = None
    min_bedrooms: int = 1
    min_size_sqm: float = 0.0
    preferred_furnished: bool = True
    pet_friendly_required: bool | None = None
    primary_neighborhoods: list[str] = field(default_factory=list)
    backup_neighborhoods: list[str] = field(default_factory=list)
    transit_anchors: list[str] = field(default_factory=list)
    park_keywords: list[str] = field(default_factory=list)
    size_tolerance_sqm: float = 8.0
    alert_score_threshold: int = 75
    watch_score_threshold: int = 55
    sender_name: str = "Patrick"
    timezone: str = "Asia/Bangkok"
    outreach_context: str = ""
    outreach_requirements: str = ""
    viewing_window_start: str | None = None
    viewing_window_end: str | None = None


@dataclass(slots=True)
class SearchSource:
    name: str
    kind: str
    url: str
    page_limit: int = 1
    detail_fetch_limit: int = 20
    enabled: bool = True
    capture_screenshot_on_conflict: bool = False
    notes: str = ""


@dataclass(slots=True)
class Listing:
    title: str
    url: str
    site_name: str
    listing_id: str | None = None
    project_name: str | None = None
    price_baht: int | None = None
    price_period: str | None = "month"
    location_text: str | None = None
    neighborhood: str | None = None
    district: str | None = None
    province: str | None = None
    nearest_bts_mrt: str | None = None
    distance_to_transit: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    size_sqm: float | None = None
    floor: str | None = None
    property_type: str | None = None
    serviced_apartment: bool = False
    furnished: bool | None = None
    pet_friendly: bool | None = None
    available_date: str | None = None
    listing_date: str | None = None
    lease_term: str | None = None
    deposit_months: int | None = None
    advance_payment_months: int | None = None
    amenities: list[str] = field(default_factory=list)
    room_amenities: list[str] = field(default_factory=list)
    project_facilities: list[str] = field(default_factory=list)
    thai_description: str | None = None
    english_summary: str | None = None
    contact_name: str | None = None
    contact_company: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    contact_line: str | None = None
    contact_whatsapp: str | None = None
    listing_source_status: str = "summary_only"
    match_score: int = 0
    fit_label: str = "watch"
    match_reasons: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    field_conflicts: list[str] = field(default_factory=list)
    discovered_from: str | None = None
    source_page: str | None = None
    last_seen_at: str | None = None
    raw_title: str | None = None
    raw_price_text: str | None = None
    raw_location_text: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)
    screenshots: list[str] = field(default_factory=list)
    dedupe_key: str = ""
    similarity_key: str = ""
    duplicate_of: str | None = None
    viewed: bool = False
    viewed_at: str | None = None
    emailed: bool = False
    emailed_at: str | None = None
    contacted: bool = False
    contacted_at: str | None = None
    not_interested: bool = False
    not_interested_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def normalized_text_blob(self) -> str:
        parts = [
            self.title,
            self.project_name,
            self.location_text,
            self.neighborhood,
            self.nearest_bts_mrt,
            self.thai_description,
            self.english_summary,
        ]
        return " ".join(part for part in parts if part)


@dataclass(slots=True)
class EmailDraft:
    listing_dedupe_key: str
    subject: str
    body: str
    created_at: str
