from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from html import unescape
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

from apartment_agent.models import Listing
from apartment_agent.utils import fetch_html, utc_now_iso

PORTAL_DOMAINS = {
    "propertyhub.in.th",
    "www.propertyhub.in.th",
    "ddproperty.com",
    "www.ddproperty.com",
    "hipflat.com",
    "www.hipflat.com",
    "propertyscout.co.th",
    "www.propertyscout.co.th",
    "thailand-property.com",
    "www.thailand-property.com",
    "renthub.in.th",
    "www.renthub.in.th",
}

SOCIAL_DOMAINS = {
    "linkedin": "linkedin.com",
    "facebook": "facebook.com",
    "instagram": "instagram.com",
}

SEARCH_ENGINE_DOMAINS = {
    "duckduckgo.com",
    "www.duckduckgo.com",
    "bing.com",
    "www.bing.com",
}

GENERIC_EMAIL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "live.com",
    "icloud.com",
    "me.com",
    "aol.com",
}


@dataclass(slots=True)
class ResearchSource:
    title: str
    url: str
    domain: str
    snippet: str = ""
    display_url: str = ""
    kind: str = "web"
    social_label: str = ""
    page_title: str = ""
    page_excerpt: str = ""
    page_emails: list[str] = field(default_factory=list)
    page_phones: list[str] = field(default_factory=list)
    is_portal: bool = False
    email_domain_match: bool = False
    exact_email_match: bool = False
    phone_match: bool = False
    fetch_status: str = "not_fetched"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class AgentResearch:
    target: str
    query: str
    summary: str
    researched_at: str
    confidence_score: int = 0
    confidence_label: str = "unknown"
    official_site_url: str = ""
    official_site_domain: str = ""
    best_source_url: str = ""
    best_source_title: str = ""
    email_domain: str = ""
    email_domain_match: bool = False
    exact_email_match: bool = False
    phone_match: bool = False
    verification_notes: list[str] = field(default_factory=list)
    sources: list[ResearchSource] = field(default_factory=list)
    social_profiles: list[ResearchSource] = field(default_factory=list)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["sources"] = [source.to_dict() for source in self.sources]
        payload["social_profiles"] = [source.to_dict() for source in self.social_profiles]
        return payload


def build_agent_research_query(listing: Listing) -> str:
    company = (listing.contact_company or "").strip()
    name = (listing.contact_name or "").strip()
    location = " ".join(part for part in [listing.project_name, listing.neighborhood, listing.location_text, listing.district] if part).strip()

    if company and name:
        base = f'"{name}" "{company}" Bangkok property rental agent'
    elif company:
        base = f'"{company}" Bangkok property rental agency'
    elif name:
        base = f'"{name}" Bangkok property rental agent'
    else:
        base = f'"{listing.site_name}" "{listing.project_name or listing.title}" rental contact'

    if location:
        return f"{base} {location}"
    return base


def build_agent_search_url(listing: Listing) -> str:
    return f"https://duckduckgo.com/?q={quote_plus(build_agent_research_query(listing))}"


def research_agent(listing: Listing, max_results: int = 5, timeout: float = 20.0) -> AgentResearch:
    query_attempts = _build_query_attempts(listing)
    query = query_attempts[0]
    sources: list[ResearchSource] = []
    for candidate in query_attempts:
        query = candidate
        sources = _collect_search_results(candidate, max_results=max_results, timeout=timeout)
        if sources:
            break

    sources = _direct_domain_sources(listing) + sources
    sources = _dedupe_sources(sources)
    sources = _enrich_sources(listing, sources, timeout=timeout)
    social_profiles = _search_social_profiles(listing, timeout=timeout)
    social_profiles = _dedupe_sources(social_profiles, key_fields=("domain", "url"))

    assessment = _assess_research(listing, sources, social_profiles)
    summary = _build_summary(listing, query, sources, social_profiles, assessment)

    return AgentResearch(
        target=_build_target(listing),
        query=query,
        summary=summary,
        researched_at=utc_now_iso(),
        confidence_score=assessment["confidence_score"],
        confidence_label=assessment["confidence_label"],
        official_site_url=assessment["official_site_url"],
        official_site_domain=assessment["official_site_domain"],
        best_source_url=assessment["best_source_url"],
        best_source_title=assessment["best_source_title"],
        email_domain=assessment["email_domain"],
        email_domain_match=assessment["email_domain_match"],
        exact_email_match=assessment["exact_email_match"],
        phone_match=assessment["phone_match"],
        verification_notes=assessment["verification_notes"],
        sources=sources,
        social_profiles=social_profiles,
    )


def collect_research_emails(payload: dict | AgentResearch | None) -> list[str]:
    if payload is None:
        return []
    if isinstance(payload, AgentResearch):
        sources = payload.sources
        social_profiles = payload.social_profiles
    else:
        sources = [ResearchSource(**source) for source in payload.get("sources", [])]
        social_profiles = [ResearchSource(**source) for source in payload.get("social_profiles", [])]

    candidates: list[str] = []
    seen: set[str] = set()
    for source in [*sources, *social_profiles]:
        for email in _extract_emails(" ".join([source.snippet, source.page_excerpt, source.url])):
            if email not in seen:
                candidates.append(email)
                seen.add(email)
        for email in source.page_emails:
            lowered = email.lower()
            if lowered not in seen:
                candidates.append(lowered)
                seen.add(lowered)
    return candidates


def _build_target(listing: Listing) -> str:
    parts = [listing.contact_name, listing.contact_company, listing.project_name or listing.location_text]
    return " | ".join(part for part in parts if part) or listing.title


def _build_query_attempts(listing: Listing) -> list[str]:
    attempts = [build_agent_research_query(listing)]
    location = " ".join(part for part in [listing.project_name, listing.neighborhood, listing.location_text] if part).strip()
    company = (listing.contact_company or "").strip()
    name = (listing.contact_name or "").strip()
    email_domain = _email_domain(listing.contact_email or "")

    if company:
        attempts.append(f'"{company}" Bangkok property')
        if location:
            attempts.append(f'"{company}" {location} rental')
    if name:
        attempts.append(f'"{name}" Bangkok property')
        if location:
            attempts.append(f'"{name}" {location} rental')
    if email_domain:
        attempts.append(f"{email_domain} Bangkok property")
    if company and email_domain:
        attempts.append(f'"{company}" {email_domain}')
    if location:
        attempts.append(f'"{listing.site_name}" "{listing.project_name or listing.title}" rental')

    deduped: list[str] = []
    for query in attempts:
        cleaned = re.sub(r"\s+", " ", query).strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped


def _direct_domain_sources(listing: Listing) -> list[ResearchSource]:
    email_domain = _email_domain(listing.contact_email or "")
    if not email_domain or email_domain in GENERIC_EMAIL_DOMAINS:
        return []
    return [
        ResearchSource(
            title=f"Direct domain check: {email_domain}",
            url=f"https://www.{email_domain}/",
            domain=f"www.{email_domain}",
            display_url=email_domain,
            kind="direct",
        ),
        ResearchSource(
            title=f"Direct domain check: {email_domain}",
            url=f"https://{email_domain}/",
            domain=email_domain,
            display_url=email_domain,
            kind="direct",
        ),
    ]


def _collect_search_results(query: str, max_results: int, timeout: float) -> list[ResearchSource]:
    sources = _search_duckduckgo_html(query, max_results=max_results, timeout=timeout)
    if sources:
        return sources
    return _search_duckduckgo_lite(query, max_results=max_results, timeout=timeout)


def _build_summary(
    listing: Listing,
    query: str,
    sources: list[ResearchSource],
    social_profiles: list[ResearchSource],
    assessment: dict,
) -> str:
    lines = [
        f"Research target: {_build_target(listing)}",
        f"Search query: {query}",
        f"Confidence: {assessment['confidence_score']} / 100 ({assessment['confidence_label']})",
        f"Listing site: {listing.site_name}",
        f"Location context: {' | '.join(part for part in [listing.project_name, listing.neighborhood, listing.location_text] if part) or '-'}",
    ]
    if listing.contact_email:
        lines.append(f"Listing email: {listing.contact_email}")
    if listing.contact_phone:
        lines.append(f"Listing phone: {listing.contact_phone}")
    if assessment["official_site_domain"]:
        lines.append(f"Official site lead: {assessment['official_site_domain']}")

    lines.extend(["", "Verification:"])
    if assessment["verification_notes"]:
        lines.extend(f"- {note}" for note in assessment["verification_notes"])
    else:
        lines.append("- No strong verification signals yet.")

    if sources:
        best_source = assessment["best_source"]
        lines.extend(
            [
                "",
                f"Best web lead: {best_source.title} ({best_source.domain})",
            ]
        )
        if best_source.page_excerpt:
            lines.append(f"Page excerpt: {best_source.page_excerpt}")
        elif best_source.snippet:
            lines.append(f"Search snippet: {best_source.snippet}")
    else:
        lines.extend(
            [
                "",
                "No live search results were parsed for this listing.",
                "Use 'Open Research Search' to review the web results manually.",
            ]
        )

    if social_profiles:
        lines.extend(["", "Social/profile hits:"])
        for source in social_profiles[:4]:
            label = source.social_label or source.domain
            lines.append(f"- {label}: {source.title} ({source.domain})")

    return "\n".join(lines)


def _assess_research(
    listing: Listing,
    sources: list[ResearchSource],
    social_profiles: list[ResearchSource],
) -> dict:
    email_domain = _email_domain(listing.contact_email or "")
    best_source = _pick_best_source(listing, sources) if sources else None
    official_source = _pick_official_source(listing, sources)
    notes: list[str] = []
    score = 0

    if sources:
        score += 10
    else:
        notes.append("No search results were captured for this listing.")

    if official_source:
        score += 22
        notes.append(f"Likely official company presence found at {official_source.domain}.")
    elif sources:
        notes.append("Results lean toward marketplace pages rather than a clear official company site.")

    exact_email_match = any(source.exact_email_match for source in sources)
    email_domain_match = any(source.email_domain_match for source in sources)
    phone_match = any(source.phone_match for source in sources)

    if exact_email_match:
        score += 24
        notes.append("The listing email appears directly on a fetched page or search result.")
    elif email_domain_match and email_domain:
        score += 16
        notes.append(f"The listing email domain matches the research results: {email_domain}.")
    elif email_domain:
        notes.append(f"The listing email domain did not clearly match the fetched sources: {email_domain}.")

    if phone_match:
        score += 18
        notes.append("The listing phone number matches a fetched page or result snippet.")
    elif listing.contact_phone:
        notes.append("The listing phone number was not verified on the fetched sources.")

    if official_source and _source_company_match(listing, official_source):
        score += 10
        notes.append("Company naming on the likely official site matches the listing details.")

    if social_profiles:
        score += min(10, 4 * len(social_profiles))
        social_labels = ", ".join(source.social_label or source.domain for source in social_profiles[:3])
        notes.append(f"Public profile-style results were also found: {social_labels}.")

    non_portal_sources = [source for source in sources if not source.is_portal]
    if sources and not non_portal_sources:
        score -= 18
        notes.append("Only portal-style results were found, which lowers confidence.")

    score = max(0, min(100, score))
    confidence_label = _confidence_label(score)

    return {
        "confidence_score": score,
        "confidence_label": confidence_label,
        "official_site_url": official_source.url if official_source else "",
        "official_site_domain": official_source.domain if official_source else "",
        "best_source_url": best_source.url if best_source else "",
        "best_source_title": best_source.title if best_source else "",
        "email_domain": email_domain,
        "email_domain_match": email_domain_match,
        "exact_email_match": exact_email_match,
        "phone_match": phone_match,
        "verification_notes": notes,
        "best_source": best_source,
    }


def _confidence_label(score: int) -> str:
    if score >= 75:
        return "strong"
    if score >= 55:
        return "moderate"
    if score >= 30:
        return "weak"
    return "low"


def _pick_best_source(listing: Listing, sources: list[ResearchSource]) -> ResearchSource:
    official_source = _pick_official_source(listing, sources)
    if official_source:
        return official_source
    if sources:
        return sources[0]
    raise ValueError("No sources available")


def _pick_official_source(listing: Listing, sources: list[ResearchSource]) -> ResearchSource | None:
    email_domain = _email_domain(listing.contact_email or "")
    for source in sources:
        if source.kind == "social" or source.is_portal:
            continue
        if email_domain and source.email_domain_match:
            return source
    for source in sources:
        if source.kind == "social" or source.is_portal:
            continue
        if _source_company_match(listing, source):
            return source
    for source in sources:
        if source.kind == "social" or source.is_portal:
            continue
        return source
    return None


def _source_company_match(listing: Listing, source: ResearchSource) -> bool:
    haystack = " ".join(
        part
        for part in [source.title, source.domain, source.snippet, source.page_title, source.page_excerpt]
        if part
    ).lower()
    company_tokens = _company_tokens(listing.contact_company or "")
    if company_tokens and any(token in haystack for token in company_tokens):
        return True
    name_tokens = _company_tokens(listing.contact_name or "")
    return bool(name_tokens and any(token in haystack for token in name_tokens))


def _dedupe_sources(
    sources: list[ResearchSource],
    key_fields: tuple[str, ...] = ("url", "domain", "title"),
) -> list[ResearchSource]:
    deduped: list[ResearchSource] = []
    seen: set[tuple[str, ...]] = set()
    for source in sources:
        if source.domain in SEARCH_ENGINE_DOMAINS:
            continue
        key = tuple(str(getattr(source, field, "")).lower() for field in key_fields)
        if key in seen:
            continue
        deduped.append(source)
        seen.add(key)
    return deduped


def _enrich_sources(listing: Listing, sources: list[ResearchSource], timeout: float) -> list[ResearchSource]:
    email = (listing.contact_email or "").strip().lower()
    email_domain = _email_domain(email)
    listing_phones = _extract_phone_numbers(listing.contact_phone or "")

    enriched: list[ResearchSource] = []
    fetched_domains: set[str] = set()
    fetch_budget = 4
    for source in sources:
        source.is_portal = source.domain in PORTAL_DOMAINS
        source.exact_email_match = bool(email and (email in source.snippet.lower() or email in source.url.lower()))
        source.email_domain_match = bool(email_domain and email_domain in source.domain)
        source.phone_match = _has_phone_overlap(listing_phones, _extract_phone_numbers(source.snippet))

        should_fetch = bool(source.url.startswith("http")) and source.domain not in fetched_domains and len(fetched_domains) < fetch_budget
        if should_fetch:
            try:
                html_text = fetch_html(source.url, timeout=max(10, int(timeout)), attempts=2)
                page_title, page_excerpt, page_emails, page_phones = _extract_page_signals(html_text)
                source.page_title = page_title
                source.page_excerpt = page_excerpt
                source.page_emails = page_emails[:5]
                source.page_phones = page_phones[:5]
                source.fetch_status = "ok"
                fetched_domains.add(source.domain)
                if page_title and (source.kind == "direct" or source.title.startswith("Direct domain check:")):
                    source.title = page_title
            except Exception:
                source.fetch_status = "error"
        if email:
            source.exact_email_match = source.exact_email_match or email in " ".join(source.page_emails).lower()
        if email_domain:
            source.email_domain_match = source.email_domain_match or any(email_domain in candidate for candidate in source.page_emails) or email_domain in source.domain
        source.phone_match = source.phone_match or _has_phone_overlap(listing_phones, source.page_phones)
        enriched.append(source)
    return enriched


def _search_social_profiles(listing: Listing, timeout: float) -> list[ResearchSource]:
    social_sources: list[ResearchSource] = []
    for label, domain in SOCIAL_DOMAINS.items():
        query = _build_social_query(listing, label)
        if not query:
            continue
        candidates = _collect_search_results(query, max_results=4, timeout=timeout)
        for source in candidates:
            if domain in source.domain:
                source.kind = "social"
                source.social_label = label.title()
                source.is_portal = False
                social_sources.append(source)
                break
    return social_sources


def _build_social_query(listing: Listing, label: str) -> str:
    company = (listing.contact_company or "").strip()
    name = (listing.contact_name or "").strip()
    email_domain = _email_domain(listing.contact_email or "")
    location = " ".join(part for part in [listing.project_name, listing.neighborhood] if part).strip()

    if company:
        return f'"{company}" {label} Bangkok property'
    if name:
        return f'"{name}" {label} Bangkok property'
    if email_domain:
        return f"{email_domain} {label} Bangkok property"
    if location:
        return f'"{listing.site_name}" "{location}" {label}'
    return ""


def _search_duckduckgo_html(query: str, max_results: int, timeout: float) -> list[ResearchSource]:
    html_text = _fetch_search_html(f"https://html.duckduckgo.com/html/?q={quote_plus(query)}", timeout=timeout)
    blocks = html_text.split('<div class="result results_links')
    results: list[ResearchSource] = []
    for block in blocks[1:]:
        title_match = re.search(r'class="result__a" href="(?P<href>[^"]+)">(?P<title>.*?)</a>', block, re.S)
        if not title_match:
            continue
        url = _resolve_result_url(title_match.group("href"))
        title = _clean_html_text(title_match.group("title"))
        url_match = re.search(r'<a class="result__url" href="[^"]+">\s*(?P<display>.*?)\s*</a>', block, re.S)
        snippet_match = re.search(r'<a class="result__snippet" href="[^"]+">(?P<snippet>.*?)</a>', block, re.S)
        source = ResearchSource(
            title=title,
            url=url,
            domain=_domain_from_url(url),
            display_url=_clean_html_text(url_match.group("display")) if url_match else _domain_from_url(url),
            snippet=_clean_html_text(snippet_match.group("snippet")) if snippet_match else "",
        )
        results.append(source)
        if len(results) >= max_results:
            break
    return results


def _search_duckduckgo_lite(query: str, max_results: int, timeout: float) -> list[ResearchSource]:
    html_text = _fetch_search_html(f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}", timeout=timeout)
    row_matches = re.finditer(
        r"class='result-link'[^>]*>(?P<title>.*?)</a>.*?class='result-snippet'>(?P<snippet>.*?)</td>",
        html_text,
        re.S,
    )
    url_matches = re.finditer(r'nofollow" href="(?P<href>[^"]+)"', html_text)
    urls = [_resolve_result_url(match.group("href")) for match in url_matches]
    results: list[ResearchSource] = []
    for index, match in enumerate(row_matches):
        if index >= len(urls):
            break
        url = urls[index]
        results.append(
            ResearchSource(
                title=_clean_html_text(match.group("title")),
                url=url,
                domain=_domain_from_url(url),
                display_url=_domain_from_url(url),
                snippet=_clean_html_text(match.group("snippet")),
            )
        )
        if len(results) >= max_results:
            break
    return results


def _extract_page_signals(html_text: str) -> tuple[str, str, list[str], list[str]]:
    title = _extract_html_title(html_text)
    meta_description = _extract_meta_description(html_text)
    body_text = _extract_body_text(html_text)
    page_text = " ".join(part for part in [title, meta_description, body_text] if part)
    emails = _extract_emails(page_text)
    phones = _extract_phone_numbers(page_text)
    excerpt = meta_description or _trim_text(body_text, 320)
    return title, excerpt, emails, phones


def _extract_html_title(html_text: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return _clean_html_text(match.group(1))


def _extract_meta_description(html_text: str) -> str:
    patterns = [
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text, re.IGNORECASE | re.DOTALL)
        if match:
            return _clean_html_text(match.group(1))
    return ""


def _extract_body_text(html_text: str) -> str:
    cleaned = re.sub(r"<script.*?</script>", " ", html_text, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<style.*?</style>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = _clean_html_text(cleaned)
    return cleaned


def _resolve_result_url(url: str) -> str:
    clean = unescape(url).replace("&amp;", "&")
    if clean.startswith("//"):
        clean = f"https:{clean}"
    elif clean.startswith("/"):
        clean = f"https://duckduckgo.com{clean}"
    parsed = urlparse(clean)
    if parsed.netloc.endswith("duckduckgo.com"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return unquote(target)
    return clean


def _fetch_search_html(url: str, timeout: float) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=max(10, timeout)) as response:
        return response.read().decode("utf-8", errors="ignore")


def _domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower()


def _clean_html_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _trim_text(value: str, length: int) -> str:
    if len(value) <= length:
        return value
    return value[: max(0, length - 3)].rstrip() + "..."


def _extract_emails(value: str) -> list[str]:
    emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", value)
    deduped: list[str] = []
    seen: set[str] = set()
    for email in emails:
        lowered = email.lower()
        if lowered not in seen:
            deduped.append(lowered)
            seen.add(lowered)
    return deduped


def _extract_phone_numbers(value: str) -> list[str]:
    matches = re.findall(r"(?:\+?\d[\d\-\s()]{6,}\d)", value or "")
    numbers: list[str] = []
    seen: set[str] = set()
    for match in matches:
        digits = re.sub(r"\D+", "", match)
        if len(digits) < 8:
            continue
        if digits not in seen:
            numbers.append(digits)
            seen.add(digits)
    return numbers


def _has_phone_overlap(left: list[str], right: list[str]) -> bool:
    if not left or not right:
        return False
    for candidate in left:
        for other in right:
            if candidate == other:
                return True
            if len(candidate) >= 8 and len(other) >= 8 and (candidate.endswith(other[-8:]) or other.endswith(candidate[-8:])):
                return True
    return False


def _company_tokens(value: str) -> list[str]:
    stop_words = {
        "thailand",
        "real",
        "estate",
        "property",
        "agency",
        "company",
        "co",
        "ltd",
        "bangkok",
        "condo",
        "residence",
    }
    tokens = re.findall(r"[a-z0-9]+", value.lower())
    return [token for token in tokens if len(token) > 2 and token not in stop_words]


def _email_domain(value: str) -> str:
    parts = value.split("@", 1)
    if len(parts) != 2:
        return ""
    return parts[1].strip().lower()
