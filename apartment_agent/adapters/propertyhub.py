from __future__ import annotations

from copy import deepcopy
from typing import Any

from apartment_agent.adapters.base import BaseAdapter
from apartment_agent.models import Listing, SearchCriteria, SearchSource
from apartment_agent.utils import (
    clean_html_fragment,
    extract_transit_mentions,
    fetch_html,
    load_next_data,
    normalize_url,
    set_query_param,
    slug_text,
    truthy_labels,
    utc_now_iso,
)

PROPERTYHUB_ROOM_LABELS = {
    "hasFurniture": "Furniture",
    "hasAir": "Air conditioner",
    "hasTV": "TV",
    "hasRefrigerator": "Fridge",
    "hasWasher": "Washing machine",
    "hasWaterHeater": "Water heater",
    "hasMicrowave": "Microwave",
    "hasKitchenStove": "Cooking stove",
    "hasKitchenHood": "Hood",
}

PROPERTYHUB_FACILITY_LABELS = {
    "lift": "Lift",
    "parking": "Parking",
    "security": "Security",
    "cctv": "CCTV",
    "pool": "Swimming Pool",
    "sauna": "Sauna",
    "fitness": "Fitness",
    "shuttle": "Shuttle Service",
    "park": "Park / BBQ Areas",
    "playground": "Kids Playground",
    "restaurant": "Restaurant",
    "allowPet": "Can raise animals",
}


class PropertyHubAdapter(BaseAdapter):
    site_name = "PropertyHub"
    base_url = "https://propertyhub.in.th"

    def collect(
        self,
        source: SearchSource,
        criteria: SearchCriteria,
        browser_capture: object | None = None,
    ) -> list[Listing]:
        if source.kind == "listing":
            listing = self._fetch_listing_detail(source.url, source, None)
            if source.capture_screenshot_on_conflict and browser_capture and listing.field_conflicts:
                self._capture(browser_capture, listing, source)
            return [listing]

        listings: list[Listing] = []
        detail_fetches = 0
        for page_number in range(1, max(1, source.page_limit) + 1):
            page_url = set_query_param(source.url, "page", page_number)
            page_data = self._fetch_page_data(page_url)
            for item in page_data["items"]:
                summary = self._summary_listing_from_item(item, source, page_url)
                if self._should_fetch_detail(summary, criteria, detail_fetches, source):
                    try:
                        summary = self._fetch_listing_detail(summary.url, source, summary)
                        detail_fetches += 1
                    except Exception as exc:  # pragma: no cover - network and site behavior
                        summary.listing_source_status = "detail_failed"
                        summary.red_flags.append(f"Detail fetch failed: {exc}")
                        if source.capture_screenshot_on_conflict and browser_capture:
                            self._capture(browser_capture, summary, source)
                listings.append(summary)

            if page_number >= page_data["total_pages"]:
                break
        return listings

    def _fetch_page_data(self, url: str) -> dict[str, Any]:
        html = fetch_html(url)
        next_data = load_next_data(html)
        page_props = next_data["props"]["pageProps"]
        listings_payload = page_props.get("listings", {})
        items = listings_payload.get("listings", [])
        pagination = listings_payload.get("pagination", {})
        return {
            "items": items,
            "total_pages": int(pagination.get("totalPages", 1) or 1),
        }

    def _summary_listing_from_item(
        self,
        item: dict[str, Any],
        source: SearchSource,
        page_url: str,
    ) -> Listing:
        project = item.get("project") or {}
        room = item.get("roomInformation") or {}
        monthly = (((item.get("price") or {}).get("forRent") or {}).get("monthly") or {})
        listing_url = self._detail_url(item.get("slug"), item.get("id"))

        listing = Listing(
            title=item.get("title") or "Untitled listing",
            raw_title=item.get("title"),
            url=listing_url,
            site_name=self.site_name,
            listing_id=str(item.get("id")) if item.get("id") is not None else None,
            project_name=project.get("nameEnglish") or project.get("name"),
            price_baht=monthly.get("price"),
            raw_price_text=f"{monthly.get('price')} THB/month" if monthly.get("price") else None,
            location_text=project.get("address"),
            raw_location_text=project.get("address"),
            bedrooms=room.get("numberOfBed"),
            bathrooms=room.get("numberOfBath"),
            size_sqm=room.get("roomArea"),
            floor=str(room.get("onFloor")) if room.get("onFloor") else None,
            property_type=item.get("propertyType"),
            listing_date=_best_listing_date(item),
            discovered_from=source.url,
            source_page=page_url,
            listing_source_status="summary_only",
            english_summary=item.get("title"),
            raw_payload={"summary": item},
        )
        self._finalize_identity(listing)
        return listing

    def _fetch_listing_detail(
        self,
        url: str,
        source: SearchSource,
        existing: Listing | None,
    ) -> Listing:
        html = fetch_html(url)
        next_data = load_next_data(html)
        detail = next_data["props"]["pageProps"]["listing"]
        base = deepcopy(existing.to_dict()) if existing else {}
        project = detail.get("project") or {}
        price = ((detail.get("price") or {}).get("forRent") or {})
        room = detail.get("roomInformation") or {}
        contact = ((detail.get("contactInformation") or [None])[0]) or {}
        detail_text = clean_html_fragment(detail.get("detail"))
        project_facilities = truthy_labels(project.get("facilities"), PROPERTYHUB_FACILITY_LABELS)
        room_amenities = truthy_labels(detail.get("amenities"), PROPERTYHUB_ROOM_LABELS)
        location_text = project.get("address") or detail.get("address") or base.get("location_text")

        listing = Listing(
            title=detail.get("title") or base.get("title") or "Untitled listing",
            raw_title=detail.get("title") or base.get("raw_title"),
            url=normalize_url(url),
            site_name=self.site_name,
            listing_id=str(detail.get("id")) if detail.get("id") is not None else base.get("listing_id"),
            project_name=project.get("nameEnglish") or project.get("name") or base.get("project_name"),
            price_baht=(((price.get("monthly") or {}).get("price")) or base.get("price_baht")),
            raw_price_text=(
                f"{(price.get('monthly') or {}).get('price')} THB/month"
                if (price.get("monthly") or {}).get("price")
                else base.get("raw_price_text")
            ),
            location_text=location_text,
            raw_location_text=location_text,
            nearest_bts_mrt=extract_transit_mentions(detail_text) or base.get("nearest_bts_mrt"),
            bedrooms=room.get("numberOfBed") or base.get("bedrooms"),
            bathrooms=room.get("numberOfBath") or base.get("bathrooms"),
            size_sqm=room.get("roomArea") or base.get("size_sqm"),
            floor=str(room.get("onFloor")) if room.get("onFloor") else base.get("floor"),
            property_type=detail.get("propertyType") or base.get("property_type"),
            serviced_apartment=(detail.get("propertyType") == "APARTMENT"),
            furnished=((detail.get("amenities") or {}).get("hasFurniture")),
            pet_friendly=((project.get("facilities") or {}).get("allowPet")),
            available_date=(price.get("monthly") or {}).get("date"),
            listing_date=_best_listing_date(detail) or base.get("listing_date"),
            lease_term=_extract_lease_term(detail_text),
            deposit_months=((price.get("deposit") or {}).get("month")),
            advance_payment_months=((price.get("advancePayment") or {}).get("month")),
            amenities=list(dict.fromkeys(room_amenities + project_facilities)),
            room_amenities=room_amenities,
            project_facilities=project_facilities,
            thai_description=_extract_thai_text(detail_text),
            english_summary=detail_text,
            contact_name=contact.get("name"),
            contact_company=contact.get("companyName") or None,
            contact_phone=", ".join(contact.get("phone", [])) or None,
            contact_email=None if contact.get("hideEmail") else contact.get("email"),
            contact_line=contact.get("lineId"),
            contact_whatsapp=contact.get("whatsapp"),
            listing_source_status="detail_ok",
            discovered_from=source.url,
            source_page=existing.source_page if existing else source.url,
            last_seen_at=utc_now_iso(),
            raw_payload={"summary": base.get("raw_payload", {}).get("summary"), "detail": detail},
        )
        self._finalize_identity(listing)
        return listing

    def _finalize_identity(self, listing: Listing) -> None:
        url_key = normalize_url(listing.url)
        project_key = slug_text(listing.project_name or listing.title)
        price_key = str(listing.price_baht or "na")
        size_key = str(int(round(listing.size_sqm))) if listing.size_sqm is not None else "na"
        beds_key = str(listing.bedrooms or "na")
        floor_key = slug_text(listing.floor)
        listing.dedupe_key = listing.listing_id or url_key
        listing.similarity_key = f"{project_key}|{beds_key}|{size_key}|{price_key}|{floor_key}"

    def _detail_url(self, slug: str | None, listing_id: str | None) -> str:
        if slug and listing_id:
            return f"{self.base_url}/en/listings/{slug}---{listing_id}"
        if listing_id:
            return f"{self.base_url}/en/listings/{listing_id}"
        return self.base_url

    def _should_fetch_detail(
        self,
        summary: Listing,
        criteria: SearchCriteria,
        detail_fetches: int,
        source: SearchSource,
    ) -> bool:
        if detail_fetches >= source.detail_fetch_limit:
            return False
        if summary.price_baht is not None and criteria.max_rent_baht is not None:
            if summary.price_baht > int(criteria.max_rent_baht * 1.2):
                return False
        if summary.bedrooms is not None and summary.bedrooms < criteria.min_bedrooms:
            return False
        if summary.size_sqm is not None and summary.size_sqm < (criteria.min_size_sqm - criteria.size_tolerance_sqm):
            return False
        return True

    def _capture(self, browser_capture: object, listing: Listing, source: SearchSource) -> None:
        output_name = f"{listing.listing_id or slug_text(listing.title)}.png"
        path = f"screenshots/{source.name.lower()}-{output_name}"
        captured = browser_capture.capture(listing.url, path)
        if captured:
            listing.screenshots.append(str(captured))


def _extract_lease_term(detail_text: str) -> str | None:
    lowered = detail_text.lower()
    if "1 year contract" in lowered:
        return "1 year contract"
    if "1 year" in lowered:
        return "1 year"
    if "6 month" in lowered:
        return "6 months"
    return None


def _extract_thai_text(detail_text: str) -> str | None:
    thai_characters = [character for character in detail_text if "\u0E00" <= character <= "\u0E7F"]
    if not thai_characters:
        return None
    return detail_text


def _best_listing_date(payload: dict[str, Any]) -> str | None:
    return (
        payload.get("modifiedAt")
        or payload.get("updatedAt")
        or payload.get("createdAt")
    )
