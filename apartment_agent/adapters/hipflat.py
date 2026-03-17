from __future__ import annotations

import re
from datetime import datetime

from apartment_agent.adapters.base import BaseAdapter
from apartment_agent.models import Listing, SearchCriteria, SearchSource
from apartment_agent.utils import (
    extract_bedrooms_from_text,
    extract_size_sqm_from_text,
    extract_transit_mentions,
    normalize_url,
    normalize_whitespace,
    set_query_param,
    slug_text,
    utc_now_iso,
)


class HipflatAdapter(BaseAdapter):
    site_name = "Hipflat"
    base_url = "https://www.hipflat.com"

    def collect(
        self,
        source: SearchSource,
        criteria: SearchCriteria,
        browser_capture: object | None = None,
    ) -> list[Listing]:
        if browser_capture is None or not hasattr(browser_capture, "snapshot"):
            raise RuntimeError(
                "Hipflat requires the Playwright browser runtime. Install `requirements-optional.txt`, then run with a verified Playwright profile if Cloudflare blocks the browser."
            )

        if source.kind == "listing":
            return [self._fetch_listing_detail(source.url, source, browser_capture)]

        listings: list[Listing] = []
        seen_urls: set[str] = set()
        detail_budget = max(1, source.detail_fetch_limit)

        for page_number in range(1, max(1, source.page_limit) + 1):
            page_url = source.url if page_number == 1 else set_query_param(source.url, "page", page_number)
            snapshot = browser_capture.snapshot(page_url)
            detail_urls = self._extract_detail_urls(snapshot.get("links", []))
            for detail_url in detail_urls:
                if detail_url in seen_urls:
                    continue
                seen_urls.add(detail_url)
                listings.append(self._fetch_listing_detail(detail_url, source, browser_capture, source_page=page_url))
                if len(seen_urls) >= detail_budget:
                    return listings
        return listings

    def _fetch_listing_detail(
        self,
        url: str,
        source: SearchSource,
        browser_capture: object,
        source_page: str | None = None,
    ) -> Listing:
        snapshot = browser_capture.snapshot(url, include_links=False)
        raw_text = str(snapshot.get("text") or "")
        text = normalize_whitespace(raw_text)
        title = self._extract_title(raw_text, str(snapshot.get("title") or ""))
        project_name = self._extract_project_name(text)
        listing = Listing(
            title=title,
            raw_title=title,
            url=normalize_url(str(snapshot.get("url") or url)),
            site_name=self.site_name,
            listing_id=self._extract_listing_id(text, url),
            project_name=project_name,
            price_baht=self._extract_price_baht(text),
            raw_price_text=self._extract_price_text(text),
            location_text=self._extract_location(title, text),
            raw_location_text=self._extract_location(title, text),
            nearest_bts_mrt=extract_transit_mentions(text),
            bedrooms=extract_bedrooms_from_text(text),
            bathrooms=self._extract_bathrooms(text),
            size_sqm=extract_size_sqm_from_text(text),
            property_type="condo",
            furnished=self._extract_furnished(text),
            listing_date=self._extract_listing_date(text),
            english_summary=self._extract_summary(text),
            contact_name=self._extract_contact_name(text),
            contact_phone=self._extract_phone(text),
            contact_email=self._extract_email(text),
            contact_line=self._extract_line(text),
            contact_whatsapp=self._extract_whatsapp(text),
            listing_source_status="browser_detail_ok",
            discovered_from=source.url,
            source_page=source_page or source.url,
            last_seen_at=utc_now_iso(),
            raw_payload={
                "browser_title": snapshot.get("title"),
                "browser_text": raw_text,
            },
        )
        self._finalize_identity(listing)
        if not listing.contact_name and "propertyscout" in text.lower():
            listing.contact_company = "PropertyScout"
        return listing

    def _extract_detail_urls(self, links: list[dict]) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        for link in links:
            href = normalize_url(str(link.get("href") or ""))
            if not href.startswith(self.base_url):
                continue
            if "/ads/" not in href:
                continue
            if href in seen:
                continue
            seen.add(href)
            urls.append(href)
        return urls

    def _finalize_identity(self, listing: Listing) -> None:
        url_key = normalize_url(listing.url)
        project_key = slug_text(listing.project_name or listing.title)
        price_key = str(listing.price_baht or "na")
        size_key = str(int(round(listing.size_sqm))) if listing.size_sqm is not None else "na"
        beds_key = str(listing.bedrooms or "na")
        listing.dedupe_key = listing.listing_id or url_key
        listing.similarity_key = f"{project_key}|{beds_key}|{size_key}|{price_key}"

    def _extract_title(self, text: str, page_title: str) -> str:
        if text:
            first_line = next((normalize_whitespace(line) for line in text.splitlines() if normalize_whitespace(line)), "")
            if first_line:
                return first_line[:180]
        cleaned_title = page_title.replace(" | Hipflat", "").strip()
        return cleaned_title or "Hipflat listing"

    def _extract_project_name(self, text: str) -> str | None:
        patterns = [
            r"part of the ([^.]+?) project",
            r"at ([A-Z0-9][A-Za-z0-9 \-()'/]+?)(?: near| in | project| condominium| condo)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return normalize_whitespace(match.group(1))
        return None

    def _extract_listing_id(self, text: str, url: str) -> str | None:
        patterns = [
            r"Listing ID\s*[:#]?\s*([A-Za-z0-9\-]+)",
            r"Unit ID\s*[:#]?\s*([A-Za-z0-9\-]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        match = re.search(r"/ads/([a-z0-9]+)", url, re.IGNORECASE)
        return match.group(1) if match else None

    def _extract_price_baht(self, text: str) -> int | None:
        match = re.search(r"([0-9][0-9,]*)\s*฿", text)
        if not match:
            match = re.search(r"Rent price\s*([0-9][0-9,]*)\s*THB", text, re.IGNORECASE)
        if not match:
            return None
        return int(match.group(1).replace(",", ""))

    def _extract_price_text(self, text: str) -> str | None:
        match = re.search(r"([0-9][0-9,]*(?:\s*฿|\s*THB)[^.,;\n]*)", text, re.IGNORECASE)
        return normalize_whitespace(match.group(1)) if match else None

    def _extract_bathrooms(self, text: str) -> int | None:
        match = re.search(r"(\d+)\s*bath(?:room)?", text, re.IGNORECASE)
        return int(match.group(1)) if match else None

    def _extract_furnished(self, text: str) -> bool | None:
        lowered = text.lower()
        if "fully furnished" in lowered or "furnished" in lowered:
            return True
        if "unfurnished" in lowered:
            return False
        return None

    def _extract_listing_date(self, text: str) -> str | None:
        match = re.search(r"Date Listed\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})", text, re.IGNORECASE)
        if match:
            raw_value = match.group(1)
            for pattern in ("%b %d, %Y", "%B %d, %Y"):
                try:
                    return datetime.strptime(raw_value, pattern).date().isoformat()
                except ValueError:
                    continue
            return raw_value
        return None

    def _extract_summary(self, text: str) -> str | None:
        patterns = [
            r"About this condo\s*(.+?)(?:Features:|Amenities:|Request Details|Schedule Viewing|Date Listed|$)",
            r"This property is a\s*(.+?)(?:Features:|Amenities:|Request Details|Schedule Viewing|Date Listed|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return normalize_whitespace(match.group(1))
        return text[:600] if text else None

    def _extract_location(self, title: str, text: str) -> str | None:
        match = re.search(r"(Chatuchak,\s*Bangkok|Phaya Thai,\s*Bangkok|Ari,\s*Bangkok|Saphan Khwai,\s*Bangkok)", text, re.IGNORECASE)
        if match:
            return normalize_whitespace(match.group(1))
        title_match = re.search(r"in ([A-Za-z \-]+,\s*Bangkok)", title, re.IGNORECASE)
        if title_match:
            return normalize_whitespace(title_match.group(1))
        return None

    def _extract_contact_name(self, text: str) -> str | None:
        match = re.search(r"Contact(?: Agent)?\s*[:\-]\s*([A-Za-z][A-Za-z .'-]{1,80})", text, re.IGNORECASE)
        return normalize_whitespace(match.group(1)) if match else None

    def _extract_phone(self, text: str) -> str | None:
        phones = re.findall(r"(?:\+66|0)[0-9][0-9 \-]{7,12}[0-9]", text)
        if not phones:
            return None
        return ", ".join(dict.fromkeys(normalize_whitespace(phone) for phone in phones))

    def _extract_email(self, text: str) -> str | None:
        match = re.search(r"([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})", text, re.IGNORECASE)
        return match.group(1) if match else None

    def _extract_line(self, text: str) -> str | None:
        match = re.search(r"LINE(?: ID)?\s*[:\-]\s*([A-Za-z0-9._\-]+)", text, re.IGNORECASE)
        return match.group(1) if match else None

    def _extract_whatsapp(self, text: str) -> str | None:
        match = re.search(r"WhatsApp\s*[:\-]\s*([+\d][0-9 \-]{7,15})", text, re.IGNORECASE)
        return normalize_whitespace(match.group(1)) if match else None
