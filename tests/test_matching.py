import unittest

from apartment_agent.matching import apply_matching
from apartment_agent.models import Listing, SearchCriteria


class MatchingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.criteria = SearchCriteria(
            max_rent_baht=55000,
            min_bedrooms=2,
            min_size_sqm=80,
            primary_neighborhoods=["Chatuchak", "Mo Chit"],
            transit_anchors=["MRT Chatuchak Park"],
            park_keywords=["park view", "Chatuchak Park"],
        )

    def test_alert_listing_scores_high(self) -> None:
        listing = Listing(
            title="M Jatujak 2BR 80 sqm near Chatuchak Park",
            url="https://example.com/mjatujak",
            site_name="PropertyHub",
            project_name="M Jatujak",
            price_baht=45000,
            location_text="Chatuchak Bangkok",
            nearest_bts_mrt="MRT Chatuchak Park",
            bedrooms=2,
            bathrooms=2,
            size_sqm=80,
            furnished=True,
            english_summary="Park view and easy walk to Chatuchak Park",
            listing_source_status="detail_ok",
        )
        listing.dedupe_key = listing.url
        listing.similarity_key = "m-jatujak|2|80|45000|na"

        apply_matching(listing, self.criteria)
        self.assertEqual(listing.fit_label, "alert")
        self.assertGreaterEqual(listing.match_score, 75)

    def test_size_conflict_is_flagged(self) -> None:
        listing = Listing(
            title="Equinox 2BR 80 sq.m 31,000/month",
            raw_title="Equinox 2BR 80 sq.m 31,000/month",
            url="https://example.com/equinox",
            site_name="PropertyHub",
            price_baht=31000,
            bedrooms=2,
            size_sqm=2.0,
            location_text="Chatuchak Bangkok",
            listing_source_status="summary_only",
        )
        listing.dedupe_key = listing.url
        listing.similarity_key = "equinox|2|2|31000|na"

        apply_matching(listing, self.criteria)
        self.assertTrue(any("Size conflict" in flag for flag in listing.red_flags))


if __name__ == "__main__":
    unittest.main()

