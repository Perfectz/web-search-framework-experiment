import unittest

from apartment_agent.agent_research import (
    PORTAL_DOMAINS,
    ResearchSource,
    _assess_research,
    _build_query_attempts,
    collect_research_emails,
)
from apartment_agent.models import Listing


class AgentResearchTests(unittest.TestCase):
    def test_build_query_attempts_include_email_domain_fallback(self) -> None:
        listing = Listing(
            title="Harmony Living",
            url="https://example.com/listing",
            site_name="PropertyHub",
            project_name="Harmony Living",
            neighborhood="Ari",
            location_text="Phaya Thai, Bangkok",
            contact_name="KC",
            contact_company="Liberal Estate (Thailand)",
            contact_email="kc_let@liberalestateth.com",
        )

        attempts = _build_query_attempts(listing)

        self.assertIn("liberalestateth.com Bangkok property", attempts)
        self.assertTrue(any('"Liberal Estate (Thailand)" Bangkok property' in query for query in attempts))

    def test_assess_research_scores_verified_official_source_high(self) -> None:
        listing = Listing(
            title="Harmony Living",
            url="https://example.com/listing",
            site_name="PropertyHub",
            project_name="Harmony Living",
            location_text="Phaya Thai, Bangkok",
            contact_name="KC",
            contact_company="Liberal Estate (Thailand)",
            contact_email="kc_let@liberalestateth.com",
            contact_phone="063-369-5994",
        )
        sources = [
            ResearchSource(
                title="Liberal Estate (Thailand) - Real Estate Agency",
                url="https://www.liberalestateth.com/",
                domain="www.liberalestateth.com",
                snippet="Bangkok real estate agency.",
                page_excerpt="Contact us at kc_let@liberalestateth.com or 0633695994 for Bangkok rentals.",
                page_emails=["kc_let@liberalestateth.com"],
                page_phones=["0633695994"],
                exact_email_match=True,
                email_domain_match=True,
                phone_match=True,
                fetch_status="ok",
            ),
            ResearchSource(
                title="Liberal Estate profile",
                url="https://www.thailand-property.com/agency/liberal-estate",
                domain="www.thailand-property.com",
                snippet="Marketplace profile.",
                is_portal=True,
            ),
        ]
        social_profiles = [
            ResearchSource(
                title="Liberal Estate (Thailand) | LinkedIn",
                url="https://www.linkedin.com/company/liberal-estate-thailand/",
                domain="www.linkedin.com",
                kind="social",
                social_label="LinkedIn",
            )
        ]

        assessment = _assess_research(listing, sources, social_profiles)

        self.assertEqual(assessment["official_site_domain"], "www.liberalestateth.com")
        self.assertTrue(assessment["email_domain_match"])
        self.assertTrue(assessment["exact_email_match"])
        self.assertTrue(assessment["phone_match"])
        self.assertGreaterEqual(assessment["confidence_score"], 75)
        self.assertEqual(assessment["confidence_label"], "strong")

    def test_assess_research_penalizes_portal_only_results(self) -> None:
        listing = Listing(
            title="Sarin Place",
            url="https://example.com/listing",
            site_name="DDproperty",
            project_name="Sarin Place",
            location_text="Lat Yao, Bangkok",
            contact_email="agent@example.com",
        )
        portal_domain = next(iter(PORTAL_DOMAINS))
        sources = [
            ResearchSource(
                title="Sarin Place for rent",
                url=f"https://{portal_domain}/listing",
                domain=portal_domain,
                snippet="Portal listing page.",
                is_portal=True,
            )
        ]

        assessment = _assess_research(listing, sources, [])

        self.assertEqual(assessment["official_site_url"], "")
        self.assertLess(assessment["confidence_score"], 30)
        self.assertEqual(assessment["confidence_label"], "low")

    def test_collect_research_emails_returns_deduped_candidates(self) -> None:
        candidates = collect_research_emails(
            {
                "sources": [
                    {
                        "title": "Liberal Estate",
                        "url": "https://www.liberalestateth.com/contact",
                        "domain": "www.liberalestateth.com",
                        "snippet": "Email kc_let@liberalestateth.com for rentals.",
                        "page_excerpt": "Reach leasing at rent@liberalestateth.com",
                        "page_emails": ["kc_let@liberalestateth.com", "rent@liberalestateth.com"],
                    }
                ],
                "social_profiles": [],
            }
        )

        self.assertEqual(candidates[0], "kc_let@liberalestateth.com")
        self.assertIn("rent@liberalestateth.com", candidates)
        self.assertEqual(len(candidates), 2)


if __name__ == "__main__":
    unittest.main()
