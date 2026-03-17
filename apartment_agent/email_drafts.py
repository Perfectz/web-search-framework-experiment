from __future__ import annotations

from apartment_agent.models import EmailDraft, Listing, SearchCriteria
from apartment_agent.utils import utc_now_iso


def build_email_draft(listing: Listing, criteria: SearchCriteria) -> EmailDraft:
    greeting = _greeting_for_listing(listing)
    subject = _subject_for_listing(listing)
    rent_text = (
        f"{listing.price_baht:,} THB per month" if listing.price_baht is not None else "the listed monthly rent"
    )
    descriptor = _descriptor_for_listing(listing)
    location = listing.project_name or listing.location_text or "the property"
    targeted_questions = _targeted_questions(listing)

    body_lines = [
        greeting,
        "",
        f"I'm interested in {descriptor} at {location}, currently listed around {rent_text}.",
        "",
    ]

    if criteria.outreach_context:
        body_lines.extend([criteria.outreach_context, ""])

    if criteria.outreach_requirements:
        body_lines.extend([criteria.outreach_requirements, ""])

    viewing_line = _viewing_window_line(criteria)
    if viewing_line:
        body_lines.extend([viewing_line, ""])

    body_lines.extend(
        [
        "Could you let me know if it is still available? I'd also like to confirm the monthly rent, lease term, deposit, and any additional fees.",
        "",
        "If possible, please also confirm whether the building entrance, elevator access, and unit layout are practical for someone with limited mobility.",
        "",
        targeted_questions,
        "",
        "Please also let me know your viewing availability.",
        "",
        "Thank you,",
        criteria.sender_name,
        ]
    )

    return EmailDraft(
        listing_dedupe_key=listing.dedupe_key,
        subject=subject,
        body="\n".join(body_lines),
        created_at=utc_now_iso(),
    )


def _greeting_for_listing(listing: Listing) -> str:
    if listing.contact_name:
        return f"Hi {listing.contact_name.split('/')[0].split(',')[0].strip()},"
    return "Hi,"


def _subject_for_listing(listing: Listing) -> str:
    size = f" {listing.size_sqm:g} sqm" if listing.size_sqm else ""
    beds = f" {listing.bedrooms}BR" if listing.bedrooms else ""
    project = listing.project_name or listing.title
    return f"Inquiry about {project}{beds}{size} rental"


def _descriptor_for_listing(listing: Listing) -> str:
    parts: list[str] = []
    if listing.bedrooms:
        parts.append(f"the {listing.bedrooms}-bedroom")
    else:
        parts.append("the listing")
    if listing.bathrooms:
        parts.append(f"{listing.bathrooms}-bath")
    if listing.size_sqm:
        parts.append(f"{listing.size_sqm:g} sqm unit")
    else:
        parts.append("unit")
    return " ".join(parts)


def _targeted_questions(listing: Listing) -> str:
    questions: list[str] = []

    if any("Size conflict" in flag for flag in listing.red_flags):
        questions.append("Could you please confirm the exact size and bedroom count?")

    if listing.serviced_apartment:
        questions.append("Could you also confirm whether there are any service or housekeeping fees?")

    location_blob = listing.normalized_text_blob().lower()
    if "chatuchak" in location_blob or "park" in location_blob or "mo chit" in location_blob:
        questions.append(
            "I'm especially interested in easy daily walking access, so I'd appreciate confirmation on the walk to Chatuchak Park / Mo Chit / Kamphaeng Phet."
        )

    if listing.furnished is not True:
        questions.append("Could you confirm the furnishing level and whether the unit is move-in ready?")

    if not questions:
        questions.append("Could you share one or two key details about the unit condition and building access?")

    return " ".join(questions[:2])


def _viewing_window_line(criteria: SearchCriteria) -> str:
    if criteria.viewing_window_start and criteria.viewing_window_end:
        return (
            f"I will be in Bangkok from {criteria.viewing_window_start} to {criteria.viewing_window_end} "
            "and would like to schedule viewings during that time if the unit is suitable."
        )
    if criteria.viewing_window_start:
        return f"I will be in Bangkok starting {criteria.viewing_window_start} and would like to schedule a viewing if the unit is suitable."
    if criteria.viewing_window_end:
        return f"I will be in Bangkok until {criteria.viewing_window_end} and would like to schedule a viewing if the unit is suitable."
    return ""
