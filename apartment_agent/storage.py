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
    viewed INTEGER NOT NULL DEFAULT 0,
    viewed_at TEXT,
    emailed INTEGER NOT NULL DEFAULT 0,
    emailed_at TEXT,
    contacted INTEGER NOT NULL DEFAULT 0,
    contacted_at TEXT,
    not_interested INTEGER NOT NULL DEFAULT 0,
    not_interested_at TEXT,
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

CREATE TABLE IF NOT EXISTS agent_research (
    listing_dedupe_key TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    summary TEXT NOT NULL,
    researched_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
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
            """
            SELECT dedupe_key, listing_date, viewed, viewed_at, emailed, emailed_at, contacted, contacted_at, not_interested, not_interested_at
            FROM listings
            WHERE dedupe_key = ?
            """,
            (listing.dedupe_key,),
        ).fetchone()

        if row:
            if listing.listing_date is None:
                listing.listing_date = row["listing_date"]
            if not listing.viewed and bool(row["viewed"]):
                listing.viewed = True
            if listing.viewed and not listing.viewed_at:
                listing.viewed_at = row["viewed_at"] or now
            elif not listing.viewed and row["viewed_at"]:
                listing.viewed = True
                listing.viewed_at = row["viewed_at"]
            if not listing.emailed and bool(row["emailed"]):
                listing.emailed = True
            if listing.emailed and not listing.emailed_at:
                listing.emailed_at = row["emailed_at"] or now
            elif not listing.emailed and row["emailed_at"]:
                listing.emailed = True
                listing.emailed_at = row["emailed_at"]
            if not listing.contacted and bool(row["contacted"]):
                listing.contacted = True
            if listing.contacted and not listing.contacted_at:
                listing.contacted_at = row["contacted_at"] or now
            elif not listing.contacted and row["contacted_at"]:
                listing.contacted = True
                listing.contacted_at = row["contacted_at"]
            if not listing.not_interested and bool(row["not_interested"]):
                listing.not_interested = True
            if listing.not_interested and not listing.not_interested_at:
                listing.not_interested_at = row["not_interested_at"] or now
            elif not listing.not_interested and row["not_interested_at"]:
                listing.not_interested = True
                listing.not_interested_at = row["not_interested_at"]
        else:
            if listing.viewed and not listing.viewed_at:
                listing.viewed_at = now
            if listing.emailed and not listing.emailed_at:
                listing.emailed_at = now
            if listing.contacted and not listing.contacted_at:
                listing.contacted_at = now
            if listing.not_interested and not listing.not_interested_at:
                listing.not_interested_at = now

        payload_json = json.dumps(listing.to_dict(), ensure_ascii=False)
        if row:
            self.connection.execute(
                """
                UPDATE listings
                SET similarity_key = ?, duplicate_of = ?, site_name = ?, listing_id = ?, url = ?, title = ?,
                    project_name = ?, price_baht = ?, fit_label = ?, match_score = ?, source_status = ?,
                    listing_date = ?, viewed = ?, viewed_at = ?, emailed = ?, emailed_at = ?, contacted = ?, contacted_at = ?, not_interested = ?, not_interested_at = ?,
                    last_seen_at = ?, payload_json = ?
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
                    int(listing.viewed),
                    listing.viewed_at,
                    int(listing.emailed),
                    listing.emailed_at,
                    int(listing.contacted),
                    listing.contacted_at,
                    int(listing.not_interested),
                    listing.not_interested_at,
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
                project_name, price_baht, fit_label, match_score, source_status, listing_date, viewed, viewed_at, emailed, emailed_at, contacted,
                contacted_at, not_interested, not_interested_at, first_seen_at,
                last_seen_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                int(listing.viewed),
                listing.viewed_at,
                int(listing.emailed),
                listing.emailed_at,
                int(listing.contacted),
                listing.contacted_at,
                int(listing.not_interested),
                listing.not_interested_at,
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
        interest_filter: str = "active",
        sort_by: str = "best_match",
        include_duplicates: bool = False,
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

        if interest_filter == "active":
            clauses.append("not_interested = 0")
        elif interest_filter == "not_interested":
            clauses.append("not_interested = 1")

        if not include_duplicates:
            clauses.append("(duplicate_of IS NULL OR duplicate_of = '')")

        if search.strip():
            like = f"%{search.strip()}%"
            clauses.append(
                "("
                "title LIKE ? OR COALESCE(project_name, '') LIKE ? OR url LIKE ? OR "
                "site_name LIKE ? OR COALESCE(listing_id, '') LIKE ?"
                ")"
            )
            params.extend([like, like, like, like, like])

        order_by = {
            "best_match": "COALESCE(match_score, 0) DESC, COALESCE(listing_date, last_seen_at) DESC",
            "newest": "COALESCE(listing_date, last_seen_at) DESC, COALESCE(match_score, 0) DESC",
            "oldest": "COALESCE(listing_date, first_seen_at) ASC, COALESCE(match_score, 0) DESC",
            "price_low": "COALESCE(price_baht, 999999999) ASC, COALESCE(match_score, 0) DESC",
            "price_high": "COALESCE(price_baht, 0) DESC, COALESCE(match_score, 0) DESC",
        }.get(sort_by, "COALESCE(match_score, 0) DESC, COALESCE(listing_date, last_seen_at) DESC")

        sql = """
        SELECT dedupe_key, duplicate_of, listing_date, viewed, viewed_at, emailed, emailed_at, contacted, contacted_at, not_interested, not_interested_at, payload_json
        FROM listings
        """
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += f" ORDER BY {order_by} LIMIT ?"
        params.append(limit)

        rows = self.connection.execute(sql, params).fetchall()
        results: list[dict] = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            payload["duplicate_of"] = row["duplicate_of"] or payload.get("duplicate_of")
            payload["listing_date"] = row["listing_date"] or payload.get("listing_date")
            payload["viewed"] = bool(row["viewed"])
            payload["viewed_at"] = row["viewed_at"] or payload.get("viewed_at")
            payload["emailed"] = bool(row["emailed"])
            payload["emailed_at"] = row["emailed_at"] or payload.get("emailed_at")
            payload["contacted"] = bool(row["contacted"])
            payload["contacted_at"] = row["contacted_at"] or payload.get("contacted_at")
            payload["not_interested"] = bool(row["not_interested"])
            payload["not_interested_at"] = row["not_interested_at"] or payload.get("not_interested_at")
            results.append(payload)
        return results

    def get_listing(self, dedupe_key: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT duplicate_of, listing_date, viewed, viewed_at, emailed, emailed_at, contacted, contacted_at, not_interested, not_interested_at, payload_json
            FROM listings
            WHERE dedupe_key = ?
            """,
            (dedupe_key,),
        ).fetchone()
        if not row:
            return None
        payload = json.loads(row["payload_json"])
        payload["duplicate_of"] = row["duplicate_of"] or payload.get("duplicate_of")
        payload["listing_date"] = row["listing_date"] or payload.get("listing_date")
        payload["viewed"] = bool(row["viewed"])
        payload["viewed_at"] = row["viewed_at"] or payload.get("viewed_at")
        payload["emailed"] = bool(row["emailed"])
        payload["emailed_at"] = row["emailed_at"] or payload.get("emailed_at")
        payload["contacted"] = bool(row["contacted"])
        payload["contacted_at"] = row["contacted_at"] or payload.get("contacted_at")
        payload["not_interested"] = bool(row["not_interested"])
        payload["not_interested_at"] = row["not_interested_at"] or payload.get("not_interested_at")
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

    def get_agent_research(self, dedupe_key: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT query, summary, researched_at, payload_json
            FROM agent_research
            WHERE listing_dedupe_key = ?
            """,
            (dedupe_key,),
        ).fetchone()
        if not row:
            return None
        payload = json.loads(row["payload_json"])
        payload["query"] = row["query"] or payload.get("query")
        payload["summary"] = row["summary"] or payload.get("summary")
        payload["researched_at"] = row["researched_at"] or payload.get("researched_at")
        return payload

    def store_agent_research(self, dedupe_key: str, payload: dict) -> None:
        query = str(payload.get("query") or "")
        summary = str(payload.get("summary") or "")
        researched_at = str(payload.get("researched_at") or utc_now_iso())
        payload_json = json.dumps(payload, ensure_ascii=False)
        self.connection.execute(
            """
            INSERT INTO agent_research (listing_dedupe_key, query, summary, researched_at, payload_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(listing_dedupe_key) DO UPDATE SET
                query = excluded.query,
                summary = excluded.summary,
                researched_at = excluded.researched_at,
                payload_json = excluded.payload_json
            """,
            (dedupe_key, query, summary, researched_at, payload_json),
        )
        self.connection.commit()

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

    def set_viewed(self, dedupe_key: str, viewed: bool) -> dict | None:
        row = self.connection.execute(
            "SELECT payload_json FROM listings WHERE dedupe_key = ?",
            (dedupe_key,),
        ).fetchone()
        if not row:
            return None

        payload = json.loads(row["payload_json"])
        viewed_at = utc_now_iso() if viewed else None
        payload["viewed"] = viewed
        payload["viewed_at"] = viewed_at
        payload_json = json.dumps(payload, ensure_ascii=False)

        self.connection.execute(
            "UPDATE listings SET viewed = ?, viewed_at = ?, payload_json = ? WHERE dedupe_key = ?",
            (int(viewed), viewed_at, payload_json, dedupe_key),
        )
        self.connection.commit()
        return payload

    def set_emailed(self, dedupe_key: str, emailed: bool) -> dict | None:
        row = self.connection.execute(
            "SELECT payload_json FROM listings WHERE dedupe_key = ?",
            (dedupe_key,),
        ).fetchone()
        if not row:
            return None

        payload = json.loads(row["payload_json"])
        emailed_at = utc_now_iso() if emailed else None
        payload["emailed"] = emailed
        payload["emailed_at"] = emailed_at
        if emailed:
            payload["contacted"] = True
            payload["contacted_at"] = payload.get("contacted_at") or emailed_at
        payload_json = json.dumps(payload, ensure_ascii=False)

        self.connection.execute(
            "UPDATE listings SET emailed = ?, emailed_at = ?, contacted = ?, contacted_at = ?, payload_json = ? WHERE dedupe_key = ?",
            (
                int(emailed),
                emailed_at,
                int(payload["contacted"]),
                payload.get("contacted_at"),
                payload_json,
                dedupe_key,
            ),
        )
        self.connection.commit()
        return payload

    def set_not_interested(self, dedupe_key: str, not_interested: bool) -> dict | None:
        row = self.connection.execute(
            "SELECT payload_json FROM listings WHERE dedupe_key = ?",
            (dedupe_key,),
        ).fetchone()
        if not row:
            return None

        payload = json.loads(row["payload_json"])
        not_interested_at = utc_now_iso() if not_interested else None
        payload["not_interested"] = not_interested
        payload["not_interested_at"] = not_interested_at
        payload_json = json.dumps(payload, ensure_ascii=False)

        self.connection.execute(
            "UPDATE listings SET not_interested = ?, not_interested_at = ?, payload_json = ? WHERE dedupe_key = ?",
            (int(not_interested), not_interested_at, payload_json, dedupe_key),
        )
        self.connection.commit()
        return payload

    def update_contact_email(self, dedupe_key: str, contact_email: str | None) -> dict | None:
        row = self.connection.execute(
            "SELECT payload_json FROM listings WHERE dedupe_key = ?",
            (dedupe_key,),
        ).fetchone()
        if not row:
            return None

        payload = json.loads(row["payload_json"])
        payload["contact_email"] = (contact_email or "").strip() or None
        payload_json = json.dumps(payload, ensure_ascii=False)

        self.connection.execute(
            "UPDATE listings SET payload_json = ? WHERE dedupe_key = ?",
            (payload_json, dedupe_key),
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
            "viewed": "INTEGER NOT NULL DEFAULT 0",
            "viewed_at": "TEXT",
            "emailed": "INTEGER NOT NULL DEFAULT 0",
            "emailed_at": "TEXT",
            "contacted": "INTEGER NOT NULL DEFAULT 0",
            "contacted_at": "TEXT",
            "not_interested": "INTEGER NOT NULL DEFAULT 0",
            "not_interested_at": "TEXT",
        }
        for column, definition in required.items():
            if column not in existing:
                self.connection.execute(f"ALTER TABLE listings ADD COLUMN {column} {definition}")

    def _find_duplicate_of(self, listing: Listing) -> str | None:
        if not listing.similarity_key:
            return self._find_fuzzy_duplicate_of(listing)
        row = self.connection.execute(
            "SELECT dedupe_key FROM listings WHERE similarity_key = ? AND dedupe_key != ? AND (duplicate_of IS NULL OR duplicate_of = '') LIMIT 1",
            (listing.similarity_key, listing.dedupe_key),
        ).fetchone()
        if row:
            return str(row["dedupe_key"])
        return self._find_fuzzy_duplicate_of(listing)

    def _find_fuzzy_duplicate_of(self, listing: Listing) -> str | None:
        project_token = _project_token(listing)
        if not project_token:
            return None
        candidates = self.connection.execute(
            """
            SELECT dedupe_key, project_name, title, price_baht, payload_json
            FROM listings
            WHERE (duplicate_of IS NULL OR duplicate_of = '')
            """
        ).fetchall()
        for row in candidates:
            if row["dedupe_key"] == listing.dedupe_key:
                continue
            payload = json.loads(row["payload_json"])
            other = Listing(**payload)
            if _looks_like_same_unit(listing, other):
                return str(row["dedupe_key"])
        return None


def _project_token(listing: Listing) -> str:
    source = (listing.project_name or listing.title or "").lower()
    cleaned = "".join(character if character.isalnum() else "-" for character in source)
    return cleaned.strip("-")


def _looks_like_same_unit(left: Listing, right: Listing) -> bool:
    if _project_token(left) != _project_token(right):
        return False
    if left.bedrooms is not None and right.bedrooms is not None and left.bedrooms != right.bedrooms:
        return False
    if left.size_sqm is not None and right.size_sqm is not None and abs(left.size_sqm - right.size_sqm) > 3:
        return False
    if left.price_baht is not None and right.price_baht is not None:
        max_price = max(left.price_baht, right.price_baht, 1)
        if abs(left.price_baht - right.price_baht) / max_price > 0.08:
            return False
    if left.floor and right.floor and left.floor != right.floor:
        return False
    return True
