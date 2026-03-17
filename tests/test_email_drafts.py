import unittest

from apartment_agent.email_drafts import build_email_draft
from apartment_agent.models import Listing, SearchCriteria


class EmailDraftTests(unittest.TestCase):
    def test_email_draft_mentions_walkability_for_chatuchak_listing(self) -> None:
        criteria = SearchCriteria(
            sender_name="Patrick",
            outreach_context="I'm looking for this apartment on behalf of my Thai girlfriend, who recently had a stroke.",
            outreach_requirements="The apartment would be for her and a live-in nurse, so I'm especially focused on accessibility, ease of movement, and whether the building and location are practical for simple daily walks.",
            viewing_window_start="April 4, 2026",
            viewing_window_end="April 26, 2026",
        )
        listing = Listing(
            title="M Jatujak 2BR 80 sqm",
            url="https://example.com/mjatujak",
            site_name="PropertyHub",
            dedupe_key="mjatujak",
            project_name="M Jatujak",
            price_baht=45000,
            bedrooms=2,
            bathrooms=2,
            size_sqm=80,
            location_text="Chatuchak Bangkok",
            english_summary="Easy walk to Chatuchak Park",
        )
        draft = build_email_draft(listing, criteria)
        self.assertIn("Chatuchak Park", draft.body)
        self.assertIn("live-in nurse", draft.body)
        self.assertIn("April 4, 2026", draft.body)
        self.assertIn("Patrick", draft.body)


if __name__ == "__main__":
    unittest.main()
