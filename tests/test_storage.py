import tempfile
import unittest
from pathlib import Path

from apartment_agent.models import EmailDraft, Listing
from apartment_agent.storage import ListingStore


class StorageTests(unittest.TestCase):
    def test_store_and_query_listing_and_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "agent.sqlite"
            listing = Listing(
                title="Harmony Living 100 sqm",
                url="https://example.com/listing",
                site_name="PropertyHub",
                listing_id="abc123",
                project_name="Harmony Living",
                price_baht=45000,
                fit_label="alert",
                match_score=88,
                listing_date="2026-03-15T10:00:00+07:00",
                dedupe_key="abc123",
                similarity_key="harmony|2|100|45000",
                contact_email="agent@example.com",
            )
            draft = EmailDraft(
                listing_dedupe_key="abc123",
                subject="Test subject",
                body="Test body",
                created_at="2026-03-16T12:00:00+00:00",
            )

            with ListingStore(db_path) as store:
                store.upsert_listing(listing)
                store.store_email_draft(draft)
                results = store.list_listings(search="Harmony", fit_label="alert")
                stored_listing = store.get_listing("abc123")
                stored_draft = store.get_latest_email_draft("abc123")
                store.set_contacted("abc123", True)
                contacted_results = store.list_listings(contacted_filter="contacted")

            self.assertEqual(len(results), 1)
            self.assertEqual(stored_listing["project_name"], "Harmony Living")
            self.assertEqual(stored_draft["subject"], "Test subject")
            self.assertEqual(contacted_results[0]["listing_date"], "2026-03-15T10:00:00+07:00")
            self.assertTrue(contacted_results[0]["contacted"])


if __name__ == "__main__":
    unittest.main()
