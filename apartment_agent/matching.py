from __future__ import annotations

from apartment_agent.models import Listing, SearchCriteria
from apartment_agent.utils import extract_bedrooms_from_text, extract_size_sqm_from_text


def apply_matching(listing: Listing, criteria: SearchCriteria) -> Listing:
    listing.field_conflicts = detect_field_conflicts(listing)
    if listing.field_conflicts:
        for conflict in listing.field_conflicts:
            if conflict not in listing.red_flags:
                listing.red_flags.append(conflict)

    score = 0
    reasons: list[str] = []
    hard_failures = 0
    text_blob = listing.normalized_text_blob().lower()

    if listing.price_baht is not None and criteria.max_rent_baht is not None:
        if listing.price_baht <= criteria.max_rent_baht:
            score += 25
            reasons.append(f"Within budget at {listing.price_baht:,} THB/month")
        else:
            hard_failures += 1
            listing.red_flags.append(
                f"Above budget at {listing.price_baht:,} THB/month"
            )

    if listing.bedrooms is not None:
        if listing.bedrooms >= criteria.min_bedrooms:
            score += 20
            reasons.append(f"{listing.bedrooms} bedrooms meets minimum")
        else:
            hard_failures += 1
            listing.red_flags.append(
                f"Only {listing.bedrooms} bedrooms, below minimum {criteria.min_bedrooms}"
            )

    if listing.size_sqm is not None:
        if listing.size_sqm >= criteria.min_size_sqm:
            score += 20
            reasons.append(f"{listing.size_sqm:g} sqm meets size target")
        elif listing.size_sqm >= max(0, criteria.min_size_sqm - criteria.size_tolerance_sqm):
            score += 8
            listing.red_flags.append(
                f"{listing.size_sqm:g} sqm is below the preferred {criteria.min_size_sqm:g} sqm floor"
            )
        else:
            hard_failures += 1
            listing.red_flags.append(
                f"{listing.size_sqm:g} sqm is materially below the preferred size"
            )

    primary_hits = _matching_terms(text_blob, criteria.primary_neighborhoods + criteria.transit_anchors)
    backup_hits = _matching_terms(text_blob, criteria.backup_neighborhoods)
    if primary_hits:
        score += 20
        reasons.append(f"Matches target area: {', '.join(primary_hits[:3])}")
    elif backup_hits:
        score += 10
        reasons.append(f"Matches backup area: {', '.join(backup_hits[:3])}")
    else:
        listing.red_flags.append("Location does not clearly match target neighborhoods/transit anchors")

    park_hits = _matching_terms(text_blob, criteria.park_keywords)
    if park_hits:
        score += 7
        reasons.append(f"Mentions walking/park cues: {', '.join(park_hits[:3])}")

    if criteria.preferred_furnished:
        if listing.furnished is True:
            score += 8
            reasons.append("Furnished")
        elif listing.furnished is False:
            listing.red_flags.append("Explicitly unfurnished")

    if criteria.pet_friendly_required is not None:
        if listing.pet_friendly == criteria.pet_friendly_required:
            score += 5
        else:
            listing.red_flags.append("Pet policy does not match stated preference")

    if listing.listing_source_status != "detail_ok":
        score -= 10
        listing.red_flags.append(f"Source status: {listing.listing_source_status}")

    if listing.field_conflicts:
        score -= 12

    listing.match_score = max(0, min(100, score))
    listing.match_reasons = _unique(reasons)
    listing.red_flags = _unique(listing.red_flags)

    if hard_failures == 0 and listing.match_score >= criteria.alert_score_threshold:
        listing.fit_label = "alert"
    elif hard_failures <= 1 and listing.match_score >= criteria.watch_score_threshold:
        listing.fit_label = "watch"
    else:
        listing.fit_label = "reject"

    return listing


def detect_field_conflicts(listing: Listing) -> list[str]:
    conflicts: list[str] = []
    title_size = extract_size_sqm_from_text(listing.raw_title or listing.title)
    if listing.size_sqm is not None and title_size is not None and abs(title_size - listing.size_sqm) > 8:
        conflicts.append(
            f"Size conflict: title suggests {title_size:g} sqm but parsed field is {listing.size_sqm:g} sqm"
        )

    title_beds = extract_bedrooms_from_text(listing.raw_title or listing.title)
    if listing.bedrooms is not None and title_beds is not None and title_beds != listing.bedrooms:
        conflicts.append(
            f"Bedroom conflict: title suggests {title_beds} bedrooms but parsed field is {listing.bedrooms}"
        )

    return conflicts


def _matching_terms(text_blob: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term and term.lower() in text_blob]


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        normalized = item.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(item)
    return output

