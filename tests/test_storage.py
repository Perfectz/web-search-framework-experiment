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
            newer_listing = Listing(
                title="M Jatujak 80 sqm",
                url="https://example.com/listing-2",
                site_name="Hipflat",
                listing_id="xyz789",
                project_name="M Jatujak",
                price_baht=48000,
                fit_label="watch",
                match_score=77,
                listing_date="2026-03-16T10:00:00+07:00",
                dedupe_key="xyz789",
                similarity_key="m-jatujak|2|80|48000",
            )
            duplicate_listing = Listing(
                title="M Jatujak 80 sqm duplicate",
                url="https://example.com/listing-3",
                site_name="PropertyHub",
                listing_id="dup001",
                project_name="M Jatujak",
                price_baht=48200,
                fit_label="alert",
                match_score=79,
                listing_date="2026-03-16T11:00:00+07:00",
                dedupe_key="dup001",
                similarity_key="m-jatujak|2|80|48000",
            )
            draft = EmailDraft(
                listing_dedupe_key="abc123",
                subject="Test subject",
                body="Test body",
                created_at="2026-03-16T12:00:00+00:00",
            )

            with ListingStore(db_path) as store:
                store.upsert_listing(listing)
                store.upsert_listing(newer_listing)
                created_duplicate, duplicate_of = store.upsert_listing(duplicate_listing)
                store.store_email_draft(draft)
                store.store_agent_research(
                    "abc123",
                    {
                        "target": "KC | Liberal Estate | Harmony Living",
                        "query": "\"KC\" \"Liberal Estate\" Bangkok property rental agent Harmony Living",
                        "summary": "Cached company research summary",
                        "researched_at": "2026-03-16T12:15:00+00:00",
                        "sources": [
                            {
                                "title": "Liberal Estate (Thailand)",
                                "url": "https://www.liberalestateth.com/",
                                "domain": "www.liberalestateth.com",
                                "snippet": "Bangkok property agency.",
                            }
                        ],
                    },
                )
                results = store.list_listings(search="Harmony", fit_label="alert")
                stored_listing = store.get_listing("abc123")
                stored_draft = store.get_latest_email_draft("abc123")
                stored_research = store.get_agent_research("abc123")
                store.update_contact_email("abc123", "newagent@example.com")
                updated_listing = store.get_listing("abc123")
                store.set_viewed("abc123", True)
                store.set_emailed("abc123", True)
                store.set_contacted("abc123", True)
                contacted_results = store.list_listings(contacted_filter="contacted")
                store.set_not_interested("abc123", True)
                hidden_results = store.list_listings(interest_filter="not_interested")
                visible_results = store.list_listings()
                all_results = store.list_listings(interest_filter="all", include_duplicates=True)
                oldest_results = store.list_listings(sort_by="oldest", interest_filter="all")
                newest_results = store.list_listings(sort_by="newest", interest_filter="all")

            self.assertEqual(len(results), 1)
            self.assertTrue(created_duplicate)
            self.assertEqual(duplicate_of, "xyz789")
            self.assertEqual(stored_listing["project_name"], "Harmony Living")
            self.assertEqual(updated_listing["contact_email"], "newagent@example.com")
            self.assertEqual(stored_draft["subject"], "Test subject")
            self.assertEqual(stored_research["summary"], "Cached company research summary")
            self.assertEqual(stored_research["sources"][0]["domain"], "www.liberalestateth.com")
            self.assertTrue(contacted_results[0]["viewed"])
            self.assertTrue(contacted_results[0]["emailed"])
            self.assertEqual(contacted_results[0]["listing_date"], "2026-03-15T10:00:00+07:00")
            self.assertTrue(contacted_results[0]["contacted"])
            self.assertEqual(len(hidden_results), 1)
            self.assertTrue(hidden_results[0]["not_interested"])
            self.assertEqual(len(visible_results), 1)
            self.assertEqual(len(all_results), 3)
            self.assertEqual(visible_results[0]["dedupe_key"], "xyz789")
            self.assertEqual(oldest_results[0]["dedupe_key"], "abc123")
            self.assertEqual(newest_results[0]["dedupe_key"], "xyz789")


if __name__ == "__main__":
    unittest.main()
