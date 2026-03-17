from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk
from urllib.parse import urlencode

from apartment_agent.config import load_criteria, load_sources
from apartment_agent.email_drafts import build_email_draft
from apartment_agent.models import Listing
from apartment_agent.pipeline import run_live
from apartment_agent.storage import ListingStore


class ApartmentAgentApp(tk.Tk):
    def __init__(
        self,
        db_path: str,
        criteria_path: str,
        sources_path: str,
        output_dir: str,
    ) -> None:
        super().__init__()
        self.db_path = db_path
        self.criteria_path = criteria_path
        self.sources_path = sources_path
        self.output_dir = output_dir
        self.criteria = load_criteria(criteria_path)
        self.selected_listing: Listing | None = None
        self.listings_by_key: dict[str, Listing] = {}
        self._search_thread: threading.Thread | None = None

        self.title("Apartment Agent")
        self.geometry("1500x900")
        self.minsize(1220, 760)
        self._configure_style()
        self._build_ui()
        self.refresh_results()

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Treeview", rowheight=24)
        style.configure("Title.TLabel", font=("Segoe UI", 15, "bold"))
        style.configure("Meta.TLabel", font=("Segoe UI", 10))
        style.configure("Section.TLabel", font=("Segoe UI", 10, "bold"))

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        toolbar = ttk.Frame(root)
        toolbar.pack(fill="x", pady=(0, 10))

        self.run_button = ttk.Button(toolbar, text="Run Search", command=self.run_search)
        self.run_button.pack(side="left")

        ttk.Button(toolbar, text="Refresh Results", command=self.refresh_results).pack(side="left", padx=(8, 0))

        ttk.Label(toolbar, text="Filter:", style="Section.TLabel").pack(side="left", padx=(18, 6))
        self.filter_var = tk.StringVar(value="all")
        filter_box = ttk.Combobox(
            toolbar,
            textvariable=self.filter_var,
            values=["all", "alert", "watch", "reject"],
            state="readonly",
            width=10,
        )
        filter_box.pack(side="left")
        filter_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_results())

        ttk.Label(toolbar, text="Contacted:", style="Section.TLabel").pack(side="left", padx=(18, 6))
        self.contacted_filter_var = tk.StringVar(value="all")
        contacted_box = ttk.Combobox(
            toolbar,
            textvariable=self.contacted_filter_var,
            values=["all", "contacted", "not_contacted"],
            state="readonly",
            width=14,
        )
        contacted_box.pack(side="left")
        contacted_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_results())

        ttk.Label(toolbar, text="Search:", style="Section.TLabel").pack(side="left", padx=(18, 6))
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(toolbar, textvariable=self.search_var, width=34)
        search_entry.pack(side="left", fill="x", expand=True)
        search_entry.bind("<Return>", lambda _event: self.refresh_results())

        ttk.Button(toolbar, text="Apply", command=self.refresh_results).pack(side="left", padx=(8, 0))

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(toolbar, textvariable=self.status_var, style="Meta.TLabel").pack(side="right")

        panes = ttk.Panedwindow(root, orient="horizontal")
        panes.pack(fill="both", expand=True)

        left = ttk.Frame(panes, padding=(0, 0, 8, 0))
        right = ttk.Frame(panes)
        panes.add(left, weight=3)
        panes.add(right, weight=4)

        self.tree = ttk.Treeview(
            left,
            columns=("fit", "contacted", "listed", "score", "price", "size", "site", "project"),
            show="headings",
            selectmode="browse",
        )
        for column, label, width in [
            ("fit", "Fit", 70),
            ("contacted", "Contacted", 84),
            ("listed", "Listed", 110),
            ("score", "Score", 70),
            ("price", "Rent", 105),
            ("size", "Sqm", 70),
            ("site", "Site", 95),
            ("project", "Project / Title", 360),
        ]:
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width, anchor="w")
        self.tree.bind("<<TreeviewSelect>>", self._on_select_listing)
        tree_scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        header = ttk.Frame(right)
        header.pack(fill="x")
        self.title_var = tk.StringVar(value="No listing selected")
        ttk.Label(header, textvariable=self.title_var, style="Title.TLabel", wraplength=760).pack(anchor="w")
        self.meta_var = tk.StringVar(value="")
        ttk.Label(header, textvariable=self.meta_var, style="Meta.TLabel", wraplength=760).pack(anchor="w", pady=(4, 10))

        actions = ttk.Frame(right)
        actions.pack(fill="x", pady=(0, 10))
        ttk.Button(actions, text="Open Listing", command=self.open_listing).pack(side="left")
        ttk.Button(actions, text="Mark Contacted", command=lambda: self.set_contacted(True)).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Mark Not Contacted", command=lambda: self.set_contacted(False)).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Regenerate Draft", command=self.regenerate_draft).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Open Gmail Draft", command=self.open_gmail_draft).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Copy Email", command=self.copy_email).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Copy Agent Info", command=self.copy_agent_info).pack(side="left", padx=(8, 0))

        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill="both", expand=True)

        self.details_tab = ttk.Frame(self.notebook, padding=10)
        self.email_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.details_tab, text="Details")
        self.notebook.add(self.email_tab, text="Email Draft")

        ttk.Label(self.details_tab, text="Agent Contact", style="Section.TLabel").pack(anchor="w")
        self.contact_text = tk.Text(self.details_tab, height=6, wrap="word")
        self.contact_text.pack(fill="x", pady=(4, 10))

        ttk.Label(self.details_tab, text="Match Reasons", style="Section.TLabel").pack(anchor="w")
        self.reasons_text = tk.Text(self.details_tab, height=6, wrap="word")
        self.reasons_text.pack(fill="x", pady=(4, 10))

        ttk.Label(self.details_tab, text="Red Flags", style="Section.TLabel").pack(anchor="w")
        self.flags_text = tk.Text(self.details_tab, height=6, wrap="word")
        self.flags_text.pack(fill="x", pady=(4, 10))

        ttk.Label(self.details_tab, text="Listing Summary", style="Section.TLabel").pack(anchor="w")
        self.summary_text = tk.Text(self.details_tab, height=14, wrap="word")
        self.summary_text.pack(fill="both", expand=True, pady=(4, 0))

        ttk.Label(self.email_tab, text="Subject", style="Section.TLabel").pack(anchor="w")
        self.subject_var = tk.StringVar()
        ttk.Entry(self.email_tab, textvariable=self.subject_var).pack(fill="x", pady=(4, 10))

        ttk.Label(self.email_tab, text="Body", style="Section.TLabel").pack(anchor="w")
        self.email_body_text = tk.Text(self.email_tab, wrap="word")
        self.email_body_text.pack(fill="both", expand=True, pady=(4, 0))

        for widget in (
            self.contact_text,
            self.reasons_text,
            self.flags_text,
            self.summary_text,
            self.email_body_text,
        ):
            widget.configure(font=("Consolas", 10))

    def refresh_results(self, select_dedupe_key: str | None = None) -> None:
        with ListingStore(self.db_path) as store:
            payloads = store.list_listings(
                search=self.search_var.get(),
                fit_label=self.filter_var.get(),
                contacted_filter=self.contacted_filter_var.get(),
                limit=300,
            )

        self.tree.delete(*self.tree.get_children())
        self.listings_by_key.clear()
        selected_item_id: str | None = None
        for index, payload in enumerate(payloads):
            listing = Listing(**payload)
            key = listing.dedupe_key or f"row-{index}"
            self.listings_by_key[key] = listing
            item_id = self.tree.insert(
                "",
                "end",
                iid=f"item-{index}",
                values=(
                    listing.fit_label,
                    "Yes" if listing.contacted else "No",
                    _format_listing_date(listing.listing_date),
                    listing.match_score,
                    _format_price(listing.price_baht),
                    _format_size(listing.size_sqm),
                    listing.site_name,
                    listing.project_name or listing.title,
                ),
                tags=(key,),
            )
            if select_dedupe_key and key == select_dedupe_key:
                selected_item_id = item_id

        if payloads:
            first_item = selected_item_id or self.tree.get_children()[0]
            self.tree.selection_set(first_item)
            self._load_tree_item(first_item)
            self.status_var.set(f"Loaded {len(payloads)} listings")
        else:
            self.selected_listing = None
            self._clear_details()
            self.status_var.set("No listings match the current filter")

    def run_search(self) -> None:
        if self._search_thread and self._search_thread.is_alive():
            return
        self.run_button.configure(state="disabled")
        self.status_var.set("Running search...")
        self._search_thread = threading.Thread(target=self._run_search_worker, daemon=True)
        self._search_thread.start()

    def _run_search_worker(self) -> None:
        try:
            criteria = load_criteria(self.criteria_path)
            sources = load_sources(self.sources_path)
            report = run_live(
                criteria=criteria,
                sources=sources,
                db_path=self.db_path,
                output_dir=self.output_dir,
            )
            self.after(0, lambda: self._on_search_complete(report, None))
        except Exception as exc:  # pragma: no cover - UI path
            self.after(0, lambda: self._on_search_complete(None, exc))

    def _on_search_complete(self, report: dict | None, error: Exception | None) -> None:
        self.run_button.configure(state="normal")
        if error is not None:
            self.status_var.set(f"Search failed: {error}")
            messagebox.showerror("Apartment Agent", f"Search failed:\n\n{error}")
            return

        self.refresh_results()
        if report is not None:
            self.status_var.set(
                f"Search complete. {len(report['alerts'])} alerts, {len(report['watch'])} watch listings."
            )

    def _on_select_listing(self, _event: object) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        self._load_tree_item(selection[0])

    def _load_tree_item(self, item_id: str) -> None:
        tags = self.tree.item(item_id, "tags")
        if not tags:
            return
        key = tags[0]
        listing = self.listings_by_key.get(key)
        if listing is None:
            return
        self.selected_listing = listing
        self._display_listing(listing)

    def _display_listing(self, listing: Listing) -> None:
        self.title_var.set(listing.title)
        self.meta_var.set(
            " | ".join(
                part
                for part in [
                    listing.project_name,
                    listing.site_name,
                    listing.fit_label.upper(),
                    f"Contacted {'Yes' if listing.contacted else 'No'}",
                    _format_listing_date(listing.listing_date),
                    f"Score {listing.match_score}",
                    _format_price(listing.price_baht),
                    _format_size(listing.size_sqm),
                ]
                if part
            )
        )

        self._set_text(self.contact_text, _contact_block(listing))
        self._set_text(self.reasons_text, "\n".join(listing.match_reasons) or "No stored match reasons.")
        self._set_text(self.flags_text, "\n".join(listing.red_flags) or "No red flags.")
        self._set_text(self.summary_text, _summary_block(listing))

        with ListingStore(self.db_path) as store:
            stored_draft = store.get_latest_email_draft(listing.dedupe_key)

        if stored_draft:
            self.subject_var.set(stored_draft["subject"])
            self._set_text(self.email_body_text, stored_draft["body"])
        else:
            draft = build_email_draft(listing, self._load_current_criteria())
            self.subject_var.set(draft.subject)
            self._set_text(self.email_body_text, draft.body)

    def regenerate_draft(self) -> None:
        if not self.selected_listing:
            return
        draft = build_email_draft(self.selected_listing, self._load_current_criteria())
        with ListingStore(self.db_path) as store:
            store.store_email_draft(draft)
        self.subject_var.set(draft.subject)
        self._set_text(self.email_body_text, draft.body)
        self.status_var.set("Draft regenerated and saved.")

    def copy_email(self) -> None:
        subject = self.subject_var.get().strip()
        body = self.email_body_text.get("1.0", "end").strip()
        if not subject and not body:
            return
        self._copy_to_clipboard(f"Subject: {subject}\n\n{body}")
        self.status_var.set("Email copied to clipboard.")

    def open_gmail_draft(self) -> None:
        if not self.selected_listing:
            return

        subject = self.subject_var.get().strip()
        body = self.email_body_text.get("1.0", "end").strip()
        if not subject and not body:
            self.regenerate_draft()
            subject = self.subject_var.get().strip()
            body = self.email_body_text.get("1.0", "end").strip()

        gmail_url = build_gmail_compose_url(
            to=self.selected_listing.contact_email,
            subject=subject,
            body=body,
        )
        webbrowser.open(gmail_url)

        if self.selected_listing.contact_email:
            self.status_var.set("Opened Gmail draft with recipient, subject, and body prefilled.")
        else:
            self.status_var.set("Opened Gmail draft with subject and body prefilled. Recipient email is missing.")

    def copy_agent_info(self) -> None:
        if not self.selected_listing:
            return
        self._copy_to_clipboard(_contact_block(self.selected_listing))
        self.status_var.set("Agent contact info copied to clipboard.")

    def set_contacted(self, contacted: bool) -> None:
        if not self.selected_listing:
            return
        with ListingStore(self.db_path) as store:
            store.set_contacted(self.selected_listing.dedupe_key, contacted)
        state_text = "contacted" if contacted else "not contacted"
        self.status_var.set(f"Marked listing as {state_text}.")
        self.refresh_results(select_dedupe_key=self.selected_listing.dedupe_key)

    def open_listing(self) -> None:
        if not self.selected_listing or not self.selected_listing.url:
            return
        webbrowser.open(self.selected_listing.url)

    def _copy_to_clipboard(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()

    def _set_text(self, widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _load_current_criteria(self):
        self.criteria = load_criteria(self.criteria_path)
        return self.criteria

    def _clear_details(self) -> None:
        self.title_var.set("No listing selected")
        self.meta_var.set("")
        for widget in (
            self.contact_text,
            self.reasons_text,
            self.flags_text,
            self.summary_text,
            self.email_body_text,
        ):
            self._set_text(widget, "")
        self.subject_var.set("")


def launch_app(
    db_path: str = "data/apartment_agent.sqlite",
    criteria_path: str = "config/criteria.json",
    sources_path: str = "config/sources.json",
    output_dir: str = "outputs",
) -> None:
    app = ApartmentAgentApp(
        db_path=db_path,
        criteria_path=criteria_path,
        sources_path=sources_path,
        output_dir=output_dir,
    )
    app.mainloop()


def _format_price(price_baht: int | None) -> str:
    return f"{price_baht:,} THB" if price_baht is not None else "-"


def _format_size(size_sqm: float | None) -> str:
    return f"{size_sqm:g} sqm" if size_sqm is not None else "-"


def _format_listing_date(value: str | None) -> str:
    if not value:
        return "-"
    return value[:10]


def _contact_block(listing: Listing) -> str:
    lines = [
        f"Name: {listing.contact_name or '-'}",
        f"Company: {listing.contact_company or '-'}",
        f"Phone: {listing.contact_phone or '-'}",
        f"Email: {listing.contact_email or '-'}",
        f"Line: {listing.contact_line or '-'}",
        f"WhatsApp: {listing.contact_whatsapp or '-'}",
    ]
    return "\n".join(lines)


def _summary_block(listing: Listing) -> str:
    parts = [
        f"URL: {listing.url}",
        f"Project: {listing.project_name or '-'}",
        f"Location: {listing.location_text or '-'}",
        f"Listing Date: {_format_listing_date(listing.listing_date)}",
        f"Contacted: {'Yes' if listing.contacted else 'No'}",
        f"Contacted At: {listing.contacted_at or '-'}",
        f"Transit: {listing.nearest_bts_mrt or '-'}",
        f"Bedrooms / Bathrooms: {listing.bedrooms or '-'} / {listing.bathrooms or '-'}",
        f"Size: {_format_size(listing.size_sqm)}",
        f"Furnished: {listing.furnished if listing.furnished is not None else '-'}",
        f"Available: {listing.available_date or '-'}",
        f"Lease Term: {listing.lease_term or '-'}",
        f"Source Status: {listing.listing_source_status}",
        f"Duplicate Of: {listing.duplicate_of or '-'}",
        "",
        "Summary:",
        listing.english_summary or "-",
    ]
    return "\n".join(parts)


def build_gmail_compose_url(to: str | None, subject: str, body: str) -> str:
    query = urlencode(
        {
            "view": "cm",
            "fs": "1",
            "to": to or "",
            "su": subject,
            "body": body,
        }
    )
    return f"https://mail.google.com/mail/?{query}"
