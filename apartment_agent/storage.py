from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from apartment_agent.models import EmailDraft, Listing
from apartment_agent.utils import ensure_parent, utc_now_iso


SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    dedupe_key TEXT PRIMARY KEY,
    similarity_key TEXT,
    duplicate_of TEXT,
    site_name TEXT NOT NULL,
    listing_id TEXT,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    project_name TEXT,
    price_baht INTEGER,
    fit_label TEXT,
    match_score INTEGER,
    source_status TEXT,
    listing_date TEXT,
    contacted INTEGER NOT NULL DEFAULT 0,
    contacted_at TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_listings_similarity_key ON listings(similarity_key);
CREATE INDEX IF NOT EXISTS idx_listings_fit_label ON listings(fit_label);

CREATE TABLE IF NOT EXISTS email_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_dedupe_key TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class ListingStore:
    def __init__(self, db_path: str | Path) -> None:
        path = ensure_parent(db_path)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)
        self._ensure_columns()
        self.connection.commit()

    def __enter__(self) -> "ListingStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def upsert_listing(self, listing: Listing) -> tuple[bool, str | None]:
        now = utc_now_iso()
        duplicate_of = self._find_duplicate_of(listing)
        row = self.connection.execute(
            "SELECT dedupe_key, listing_date, contacted, contacted_at FROM listings WHERE dedupe_key = ?",
            (listing.dedupe_key,),
        ).fetchone()

        if row:
            if listing.listing_date is None:
                listing.listing_date = row["listing_date"]
            if not listing.contacted and bool(row["contacted"]):
                listing.contacted = True
            if listing.contacted and not listing.contacted_at:
                listing.contacted_at = row["contacted_at"] or now
            elif not listing.contacted and row["contacted_at"]:
                listing.contacted = True
                listing.contacted_at = row["contacted_at"]
        elif listing.contacted and not listing.contacted_at:
            listing.contacted_at = now

        payload_json = json.dumps(listing.to_dict(), ensure_ascii=False)
        if row:
            self.connection.execute(
                """
                UPDATE listings
                SET similarity_key = ?, duplicate_of = ?, site_name = ?, listing_id = ?, url = ?, title = ?,
                    project_name = ?, price_baht = ?, fit_label = ?, match_score = ?, source_status = ?,
                    listing_date = ?, contacted = ?, contacted_at = ?, last_seen_at = ?, payload_json = ?
                WHERE dedupe_key = ?
                """,
                (
                    listing.similarity_key,
                    duplicate_of,
                    listing.site_name,
                    listing.listing_id,
                    listing.url,
                    listing.title,
                    listing.project_name,
                    listing.price_baht,
                    listing.fit_label,
                    listing.match_score,
                    listing.listing_source_status,
                    listing.listing_date,
                    int(listing.contacted),
                    listing.contacted_at,
                    now,
                    payload_json,
                    listing.dedupe_key,
                ),
            )
            self.connection.commit()
            return False, duplicate_of

        self.connection.execute(
            """
            INSERT INTO listings (
                dedupe_key, similarity_key, duplicate_of, site_name, listing_id, url, title,
                project_name, price_baht, fit_label, match_score, source_status, listing_date, contacted,
                contacted_at, first_seen_at,
                last_seen_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                listing.dedupe_key,
                listing.similarity_key,
                duplicate_of,
                listing.site_name,
                listing.listing_id,
                listing.url,
                listing.title,
                listing.project_name,
                listing.price_baht,
                listing.fit_label,
                listing.match_score,
                listing.listing_source_status,
                listing.listing_date,
                int(listing.contacted),
                listing.contacted_at,
                now,
                now,
                payload_json,
            ),
        )
        self.connection.commit()
        return True, duplicate_of

    def store_email_draft(self, draft: EmailDraft) -> None:
        self.connection.execute(
            "INSERT INTO email_drafts (listing_dedupe_key, subject, body, created_at) VALUES (?, ?, ?, ?)",
            (draft.listing_dedupe_key, draft.subject, draft.body, draft.created_at),
        )
        self.connection.commit()

    def list_listings(
        self,
        search: str = "",
        fit_label: str = "all",
        contacted_filter: str = "all",
        limit: int = 250,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list[object] = []

        if fit_label and fit_label != "all":
            clauses.append("fit_label = ?")
            params.append(fit_label)

        if contacted_filter == "contacted":
            clauses.append("contacted = 1")
        elif contacted_filter == "not_contacted":
            clauses.append("contacted = 0")

        if search.strip():
            like = f"%{search.strip()}%"
            clauses.append(
                "("
                "title LIKE ? OR COALESCE(project_name, '') LIKE ? OR url LIKE ? OR "
                "site_name LIKE ? OR COALESCE(listing_id, '') LIKE ?"
                ")"
            )
            params.extend([like, like, like, like, like])

        sql = "SELECT dedupe_key, duplicate_of, listing_date, contacted, contacted_at, payload_json FROM listings"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY COALESCE(match_score, 0) DESC, COALESCE(listing_date, last_seen_at) DESC LIMIT ?"
        params.append(limit)

        rows = self.connection.execute(sql, params).fetchall()
        results: list[dict] = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            payload["duplicate_of"] = row["duplicate_of"] or payload.get("duplicate_of")
            payload["listing_date"] = row["listing_date"] or payload.get("listing_date")
            payload["contacted"] = bool(row["contacted"])
            payload["contacted_at"] = row["contacted_at"] or payload.get("contacted_at")
            results.append(payload)
        return results

    def get_listing(self, dedupe_key: str) -> dict | None:
        row = self.connection.execute(
            "SELECT duplicate_of, listing_date, contacted, contacted_at, payload_json FROM listings WHERE dedupe_key = ?",
            (dedupe_key,),
        ).fetchone()
        if not row:
            return None
        payload = json.loads(row["payload_json"])
        payload["duplicate_of"] = row["duplicate_of"] or payload.get("duplicate_of")
        payload["listing_date"] = row["listing_date"] or payload.get("listing_date")
        payload["contacted"] = bool(row["contacted"])
        payload["contacted_at"] = row["contacted_at"] or payload.get("contacted_at")
        return payload

    def get_latest_email_draft(self, dedupe_key: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT subject, body, created_at
            FROM email_drafts
            WHERE listing_dedupe_key = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (dedupe_key,),
        ).fetchone()
        if not row:
            return None
        return {
            "subject": row["subject"],
            "body": row["body"],
            "created_at": row["created_at"],
        }

    def set_contacted(self, dedupe_key: str, contacted: bool) -> dict | None:
        row = self.connection.execute(
            "SELECT payload_json FROM listings WHERE dedupe_key = ?",
            (dedupe_key,),
        ).fetchone()
        if not row:
            return None

        payload = json.loads(row["payload_json"])
        contacted_at = utc_now_iso() if contacted else None
        payload["contacted"] = contacted
        payload["contacted_at"] = contacted_at
        payload_json = json.dumps(payload, ensure_ascii=False)

        self.connection.execute(
            "UPDATE listings SET contacted = ?, contacted_at = ?, payload_json = ? WHERE dedupe_key = ?",
            (int(contacted), contacted_at, payload_json, dedupe_key),
        )
        self.connection.commit()
        return payload

    def _ensure_columns(self) -> None:
        existing = {
            row["name"]
            for row in self.connection.execute("PRAGMA table_info(listings)").fetchall()
        }
        required = {
            "listing_date": "TEXT",
            "contacted": "INTEGER NOT NULL DEFAULT 0",
            "contacted_at": "TEXT",
        }
        for column, definition in required.items():
            if column not in existing:
                self.connection.execute(f"ALTER TABLE listings ADD COLUMN {column} {definition}")

    def _find_duplicate_of(self, listing: Listing) -> str | None:
        if not listing.similarity_key:
            return None
        row = self.connection.execute(
            "SELECT dedupe_key FROM listings WHERE similarity_key = ? AND dedupe_key != ? LIMIT 1",
            (listing.similarity_key, listing.dedupe_key),
        ).fetchone()
        if not row:
            return None
        return str(row["dedupe_key"])
