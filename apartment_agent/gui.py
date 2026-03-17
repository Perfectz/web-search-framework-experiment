from __future__ import annotations

import os
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
        self.colors = {
            "bg": "#F4EFE8",
            "card": "#FFFDF9",
            "panel": "#F7F2EA",
            "border": "#DDD5C8",
            "text": "#182230",
            "muted": "#667085",
            "hero": "#18324A",
            "hero_alt": "#234765",
            "accent": "#0F766E",
            "accent_hover": "#115E59",
            "accent_soft": "#D9F2EE",
            "amber": "#B45309",
            "amber_soft": "#FFF1DE",
            "blue": "#1D4ED8",
            "blue_hover": "#1E40AF",
            "blue_soft": "#E7EEFF",
            "danger": "#B42318",
            "danger_soft": "#FDECEC",
            "tree_header": "#F5F0E7",
            "white": "#FFFFFF",
        }
        self.status_var = tk.StringVar(value="Ready")

        self.title("Apartment Agent Workspace")
        self.geometry("1520x940")
        self.minsize(1260, 800)
        self.configure(bg=self.colors["bg"])
        self._configure_style()
        self._build_ui()
        self.refresh_results()

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Accent.TButton",
            background=self.colors["accent"],
            foreground=self.colors["white"],
            bordercolor=self.colors["accent"],
            darkcolor=self.colors["accent"],
            lightcolor=self.colors["accent"],
            focusthickness=0,
            padding=(16, 10),
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Accent.TButton",
            background=[("active", self.colors["accent_hover"]), ("pressed", self.colors["accent_hover"])],
            foreground=[("!disabled", self.colors["white"])],
        )
        style.configure(
            "Blue.TButton",
            background=self.colors["blue"],
            foreground=self.colors["white"],
            bordercolor=self.colors["blue"],
            darkcolor=self.colors["blue"],
            lightcolor=self.colors["blue"],
            focusthickness=0,
            padding=(16, 10),
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Blue.TButton",
            background=[("active", self.colors["blue_hover"]), ("pressed", self.colors["blue_hover"])],
            foreground=[("!disabled", self.colors["white"])],
        )
        style.configure(
            "Warm.TButton",
            background=self.colors["amber_soft"],
            foreground=self.colors["amber"],
            bordercolor=self.colors["amber_soft"],
            darkcolor=self.colors["amber_soft"],
            lightcolor=self.colors["amber_soft"],
            focusthickness=0,
            padding=(14, 10),
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Warm.TButton",
            background=[("active", "#FBE3C1"), ("pressed", "#F5D6A4")],
            foreground=[("!disabled", self.colors["amber"])],
        )
        style.configure(
            "Danger.TButton",
            background=self.colors["danger_soft"],
            foreground=self.colors["danger"],
            bordercolor=self.colors["danger_soft"],
            darkcolor=self.colors["danger_soft"],
            lightcolor=self.colors["danger_soft"],
            focusthickness=0,
            padding=(14, 10),
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Danger.TButton",
            background=[("active", "#F7D7D7"), ("pressed", "#F2CACA")],
            foreground=[("!disabled", self.colors["danger"])],
        )
        style.configure(
            "Ghost.TButton",
            background=self.colors["card"],
            foreground=self.colors["text"],
            bordercolor=self.colors["border"],
            darkcolor=self.colors["card"],
            lightcolor=self.colors["card"],
            focusthickness=0,
            padding=(14, 10),
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Ghost.TButton",
            background=[("active", self.colors["panel"]), ("pressed", self.colors["panel"])],
            foreground=[("!disabled", self.colors["text"])],
        )
        style.configure(
            "Filter.TCombobox",
            fieldbackground=self.colors["card"],
            background=self.colors["card"],
            foreground=self.colors["text"],
            bordercolor=self.colors["border"],
            arrowsize=14,
            padding=6,
        )
        style.map(
            "Filter.TCombobox",
            fieldbackground=[("readonly", self.colors["card"])],
            selectbackground=[("readonly", self.colors["card"])],
            selectforeground=[("readonly", self.colors["text"])],
        )
        style.configure(
            "Search.TEntry",
            fieldbackground=self.colors["card"],
            foreground=self.colors["text"],
            bordercolor=self.colors["border"],
            padding=8,
        )
        style.configure(
            "Treeview",
            background=self.colors["card"],
            fieldbackground=self.colors["card"],
            foreground=self.colors["text"],
            bordercolor=self.colors["border"],
            lightcolor=self.colors["border"],
            darkcolor=self.colors["border"],
            rowheight=34,
            relief="flat",
            font=("Segoe UI", 10),
        )
        style.map(
            "Treeview",
            background=[("selected", self.colors["hero_alt"])],
            foreground=[("selected", self.colors["white"])],
        )
        style.configure(
            "Treeview.Heading",
            background=self.colors["tree_header"],
            foreground=self.colors["text"],
            borderwidth=0,
            relief="flat",
            padding=(10, 10),
            font=("Segoe UI Semibold", 10),
        )
        style.configure("TNotebook", background=self.colors["card"], borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=self.colors["panel"],
            foreground=self.colors["muted"],
            padding=(16, 10),
            font=("Segoe UI Semibold", 10),
            borderwidth=0,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", self.colors["card"]), ("active", self.colors["panel"])],
            foreground=[("selected", self.colors["text"]), ("active", self.colors["text"])],
        )

    def _build_ui(self) -> None:
        root = tk.Frame(self, bg=self.colors["bg"], padx=18, pady=18)
        root.pack(fill="both", expand=True)

        hero = self._card(root, bg=self.colors["hero"], border=self.colors["hero"], padx=24, pady=22)
        hero.pack(fill="x", pady=(0, 14))
        hero_left = tk.Frame(hero, bg=self.colors["hero"])
        hero_left.pack(side="left", fill="x", expand=True)
        tk.Label(
            hero_left,
            text="APARTMENT AGENT CONSOLE",
            bg=self.colors["hero"],
            fg="#B7C8D6",
            font=("Segoe UI Semibold", 10),
        ).pack(anchor="w")
        tk.Label(
            hero_left,
            text="Search, rank, contact, and track Bangkok apartment leads",
            bg=self.colors["hero"],
            fg=self.colors["white"],
            font=("Segoe UI Semibold", 24),
        ).pack(anchor="w", pady=(8, 4))
        tk.Label(
            hero_left,
            text="A local workflow app for web search results, agent outreach drafts, and contact-state tracking.",
            bg=self.colors["hero"],
            fg="#D6E0E8",
            font=("Segoe UI", 11),
        ).pack(anchor="w")

        hero_right = tk.Frame(hero, bg=self.colors["hero"])
        hero_right.pack(side="right", anchor="n")
        self.status_badge = tk.Label(
            hero_right,
            textvariable=self.status_var,
            bg="#244761",
            fg=self.colors["white"],
            font=("Segoe UI Semibold", 10),
            padx=14,
            pady=8,
        )
        self.status_badge.pack(anchor="e")

        metrics_row = tk.Frame(root, bg=self.colors["bg"])
        metrics_row.pack(fill="x", pady=(0, 14))
        self.loaded_var = tk.StringVar(value="0")
        self.alerts_var = tk.StringVar(value="0")
        self.watch_var = tk.StringVar(value="0")
        self.contacted_var = tk.StringVar(value="0")
        self._make_metric_card(metrics_row, "Loaded", self.loaded_var, self.colors["blue_soft"], self.colors["blue"]).pack(side="left", fill="x", expand=True, padx=(0, 10))
        self._make_metric_card(metrics_row, "Alerts", self.alerts_var, self.colors["accent_soft"], self.colors["accent"]).pack(side="left", fill="x", expand=True, padx=(0, 10))
        self._make_metric_card(metrics_row, "Watch", self.watch_var, self.colors["amber_soft"], self.colors["amber"]).pack(side="left", fill="x", expand=True, padx=(0, 10))
        self._make_metric_card(metrics_row, "Contacted", self.contacted_var, "#EAE8FF", "#4F46E5").pack(side="left", fill="x", expand=True)

        controls = self._card(root, padx=18, pady=16)
        controls.pack(fill="x", pady=(0, 14))
        filters_row = tk.Frame(controls, bg=self.colors["card"])
        filters_row.pack(fill="x")

        self._field_label(filters_row, "Fit").pack(side="left")
        self.filter_var = tk.StringVar(value="all")
        self.filter_box = ttk.Combobox(filters_row, textvariable=self.filter_var, values=["all", "alert", "watch", "reject"], state="readonly", width=10, style="Filter.TCombobox")
        self.filter_box.pack(side="left", padx=(8, 16))
        self.filter_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_results())

        self._field_label(filters_row, "Contacted").pack(side="left")
        self.contacted_filter_var = tk.StringVar(value="all")
        self.contacted_box = ttk.Combobox(filters_row, textvariable=self.contacted_filter_var, values=["all", "contacted", "not_contacted"], state="readonly", width=14, style="Filter.TCombobox")
        self.contacted_box.pack(side="left", padx=(8, 16))
        self.contacted_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_results())

        self._field_label(filters_row, "Interest").pack(side="left")
        self.interest_filter_var = tk.StringVar(value="active")
        self.interest_box = ttk.Combobox(filters_row, textvariable=self.interest_filter_var, values=["active", "all", "not_interested"], state="readonly", width=16, style="Filter.TCombobox")
        self.interest_box.pack(side="left", padx=(8, 16))
        self.interest_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_results())

        self._field_label(filters_row, "Sort").pack(side="left")
        self.sort_var = tk.StringVar(value="best_match")
        self.sort_box = ttk.Combobox(filters_row, textvariable=self.sort_var, values=["best_match", "newest", "oldest", "price_low", "price_high"], state="readonly", width=12, style="Filter.TCombobox")
        self.sort_box.pack(side="left", padx=(8, 16))
        self.sort_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_results())

        self._field_label(filters_row, "Search").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(filters_row, textvariable=self.search_var, width=28, style="Search.TEntry")
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(8, 10))
        self.search_entry.bind("<Return>", lambda _event: self.refresh_results())

        actions_row = tk.Frame(controls, bg=self.colors["card"])
        actions_row.pack(fill="x", pady=(14, 0))
        self.run_button = ttk.Button(actions_row, text="Run Search", style="Accent.TButton", command=self.run_search)
        self.run_button.pack(side="left")
        ttk.Button(actions_row, text="Refresh Results", style="Ghost.TButton", command=self.refresh_results).pack(side="left", padx=(8, 0))
        ttk.Button(actions_row, text="Apply Filters", style="Blue.TButton", command=self.refresh_results).pack(side="left", padx=(8, 0))
        ttk.Button(actions_row, text="Reset", style="Ghost.TButton", command=self.reset_filters).pack(side="left", padx=(8, 0))
        self.controls_meta_var = tk.StringVar(value="Use filters to narrow results by fit, date order, contact state, and hidden-state visibility.")
        tk.Label(actions_row, textvariable=self.controls_meta_var, bg=self.colors["card"], fg=self.colors["muted"], font=("Segoe UI", 10)).pack(side="right")

        panes = ttk.Panedwindow(root, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left = tk.Frame(panes, bg=self.colors["bg"])
        right = tk.Frame(panes, bg=self.colors["bg"])
        panes.add(left, weight=3)
        panes.add(right, weight=4)

        results_card = self._card(left, padx=14, pady=14)
        results_card.pack(fill="both", expand=True, padx=(0, 8))
        results_header = tk.Frame(results_card, bg=self.colors["card"])
        results_header.pack(fill="x", pady=(0, 10))
        tk.Label(results_header, text="Results", bg=self.colors["card"], fg=self.colors["text"], font=("Segoe UI Semibold", 15)).pack(anchor="w")
        self.results_meta_var = tk.StringVar(value="No listings loaded yet.")
        tk.Label(results_header, textvariable=self.results_meta_var, bg=self.colors["card"], fg=self.colors["muted"], font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 0))

        tree_shell = tk.Frame(results_card, bg=self.colors["card"])
        tree_shell.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_shell, columns=("fit", "contacted", "listed", "score", "price", "size", "site", "project"), show="headings", selectmode="browse")
        for column, label, width in [("fit", "Fit", 78), ("contacted", "Contacted", 92), ("listed", "Listed", 108), ("score", "Score", 72), ("price", "Rent", 110), ("size", "Sqm", 70), ("site", "Site", 92), ("project", "Project / Title", 360)]:
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width, anchor="w")
        self.tree.tag_configure("alert", background="#EAF8F5")
        self.tree.tag_configure("watch", background="#FFF7EB")
        self.tree.tag_configure("reject", foreground="#8892A0")
        self.tree.tag_configure("contacted", foreground="#6B7280")
        self.tree.tag_configure("not_interested", background="#FDECEC", foreground="#8A1C14")
        self.tree.bind("<<TreeviewSelect>>", self._on_select_listing)
        tree_scroll = ttk.Scrollbar(tree_shell, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        detail_card = self._card(right, padx=16, pady=16)
        detail_card.pack(fill="both", expand=True)

        detail_header = tk.Frame(detail_card, bg=self.colors["card"])
        detail_header.pack(fill="x", pady=(0, 12))
        detail_header.columnconfigure(0, weight=1)
        self.title_var = tk.StringVar(value="No listing selected")
        tk.Label(
            detail_header,
            textvariable=self.title_var,
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI Semibold", 18),
            wraplength=720,
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        self.selection_badge = tk.Label(
            detail_header,
            text="Waiting",
            bg=self.colors["panel"],
            fg=self.colors["muted"],
            font=("Segoe UI Semibold", 10),
            padx=12,
            pady=7,
        )
        self.selection_badge.grid(row=0, column=1, sticky="e", padx=(12, 0))
        self.meta_var = tk.StringVar(value="")
        tk.Label(
            detail_header,
            textvariable=self.meta_var,
            bg=self.colors["card"],
            fg=self.colors["muted"],
            font=("Segoe UI", 10),
            wraplength=820,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        action_card = self._card(detail_card, bg=self.colors["panel"], border=self.colors["border"], padx=12, pady=12)
        action_card.pack(fill="x", pady=(0, 12))
        primary_actions = tk.Frame(action_card, bg=self.colors["panel"])
        primary_actions.pack(fill="x")
        self.open_listing_button = ttk.Button(primary_actions, text="Open Listing", style="Ghost.TButton", command=self.open_listing)
        self.open_listing_button.pack(side="left")
        self.open_gmail_button = ttk.Button(primary_actions, text="Open Gmail Draft", style="Blue.TButton", command=self.open_gmail_draft)
        self.open_gmail_button.pack(side="left", padx=(8, 0))
        self.regenerate_draft_button = ttk.Button(primary_actions, text="Regenerate Draft", style="Accent.TButton", command=self.regenerate_draft)
        self.regenerate_draft_button.pack(side="left", padx=(8, 0))
        self.copy_email_button = ttk.Button(primary_actions, text="Copy Email", style="Ghost.TButton", command=self.copy_email)
        self.copy_email_button.pack(side="left", padx=(8, 0))

        secondary_actions = tk.Frame(action_card, bg=self.colors["panel"])
        secondary_actions.pack(fill="x", pady=(10, 0))
        ttk.Button(secondary_actions, text="Mark Contacted", style="Warm.TButton", command=lambda: self.set_contacted(True)).pack(side="left")
        ttk.Button(secondary_actions, text="Mark Not Contacted", style="Ghost.TButton", command=lambda: self.set_contacted(False)).pack(side="left", padx=(8, 0))
        self.hide_listing_button = ttk.Button(secondary_actions, text="Hide Listing", style="Danger.TButton", command=lambda: self.set_not_interested(True))
        self.hide_listing_button.pack(side="left", padx=(8, 0))
        self.restore_listing_button = ttk.Button(secondary_actions, text="Restore Listing", style="Ghost.TButton", command=lambda: self.set_not_interested(False))
        self.restore_listing_button.pack(side="left", padx=(8, 0))
        ttk.Button(secondary_actions, text="Copy Agent Info", style="Ghost.TButton", command=self.copy_agent_info).pack(side="left", padx=(8, 0))

        notebook_card = self._card(detail_card, padx=12, pady=12)
        notebook_card.pack(fill="both", expand=True)
        self.notebook = ttk.Notebook(notebook_card)
        self.notebook.pack(fill="both", expand=True)

        self.details_tab = tk.Frame(self.notebook, bg=self.colors["card"])
        self.details_tab.columnconfigure(0, weight=3)
        self.details_tab.columnconfigure(1, weight=2)
        self.details_tab.rowconfigure(0, weight=1)
        self.summary_text = self._text_panel(self.details_tab, "Listing Summary")
        self.summary_text.master.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.contact_text = self._text_panel(self.details_tab, "Agent Contact")
        self.contact_text.master.grid(row=0, column=1, sticky="nsew")
        self.notebook.add(self.details_tab, text="Overview")

        self.review_tab = tk.Frame(self.notebook, bg=self.colors["card"])
        self.review_tab.columnconfigure(0, weight=1)
        self.review_tab.columnconfigure(1, weight=1)
        self.review_tab.rowconfigure(0, weight=1)
        self.reasons_text = self._text_panel(self.review_tab, "Why It Matches")
        self.reasons_text.master.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.flags_text = self._text_panel(self.review_tab, "Risks And Gaps")
        self.flags_text.master.grid(row=0, column=1, sticky="nsew")
        self.notebook.add(self.review_tab, text="Review")

        self.email_tab = tk.Frame(self.notebook, bg=self.colors["card"])
        self.email_tab.columnconfigure(0, weight=1)
        self.email_tab.rowconfigure(2, weight=1)
        self._field_label(self.email_tab, "Email Subject").grid(row=0, column=0, sticky="w")
        self.subject_var = tk.StringVar()
        self.subject_entry = ttk.Entry(self.email_tab, textvariable=self.subject_var, style="Search.TEntry")
        self.subject_entry.grid(row=1, column=0, sticky="ew", pady=(6, 10))
        self.email_body_text = self._text_panel(self.email_tab, "Email Body", readonly=False)
        self.email_body_text.master.grid(row=2, column=0, sticky="nsew")
        self.notebook.add(self.email_tab, text="Email Draft")

    def reset_filters(self) -> None:
        self.filter_var.set("all")
        self.contacted_filter_var.set("all")
        self.interest_filter_var.set("active")
        self.sort_var.set("best_match")
        self.search_var.set("")
        self.refresh_results()

    def _set_status(self, message: str, tone: str = "neutral") -> None:
        tone_map = {
            "neutral": ("#244761", self.colors["white"]),
            "accent": (self.colors["accent"], self.colors["white"]),
            "blue": (self.colors["blue"], self.colors["white"]),
            "warm": (self.colors["amber_soft"], self.colors["amber"]),
            "danger": (self.colors["danger_soft"], self.colors["danger"]),
        }
        bg, fg = tone_map.get(tone, tone_map["neutral"])
        self.status_var.set(message)
        self.status_badge.configure(bg=bg, fg=fg)

    def _update_metrics(self, listings: list[Listing]) -> None:
        self.loaded_var.set(str(len(listings)))
        self.alerts_var.set(str(sum(1 for listing in listings if listing.fit_label == "alert")))
        self.watch_var.set(str(sum(1 for listing in listings if listing.fit_label == "watch")))
        self.contacted_var.set(str(sum(1 for listing in listings if listing.contacted)))

    def _set_selection_badge(self, listing: Listing | None) -> None:
        if listing is None:
            self.selection_badge.configure(text="Waiting", bg=self.colors["panel"], fg=self.colors["muted"])
            return

        if listing.not_interested:
            bg = self.colors["danger_soft"]
            fg = self.colors["danger"]
        elif listing.fit_label == "alert":
            bg = self.colors["accent_soft"]
            fg = self.colors["accent"]
        elif listing.fit_label == "watch":
            bg = self.colors["amber_soft"]
            fg = self.colors["amber"]
        else:
            bg = "#EBEEF2"
            fg = self.colors["muted"]

        label = listing.fit_label.upper()
        if listing.not_interested:
            label = f"{label} / HIDDEN"
        if listing.contacted:
            label = f"{label} / CONTACTED"
        self.selection_badge.configure(text=label, bg=bg, fg=fg)

    def _card(
        self,
        parent: tk.Misc,
        *,
        bg: str | None = None,
        border: str | None = None,
        padx: int = 16,
        pady: int = 16,
    ) -> tk.Frame:
        frame = tk.Frame(
            parent,
            bg=bg or self.colors["card"],
            highlightbackground=border or self.colors["border"],
            highlightthickness=1,
            bd=0,
            padx=padx,
            pady=pady,
        )
        return frame

    def _field_label(self, parent: tk.Misc, text: str) -> tk.Label:
        return tk.Label(
            parent,
            text=text.upper(),
            bg=parent.cget("bg"),
            fg=self.colors["muted"],
            font=("Segoe UI Semibold", 9),
        )

    def _make_metric_card(
        self,
        parent: tk.Misc,
        label: str,
        value_var: tk.StringVar,
        bg: str,
        accent: str,
    ) -> tk.Frame:
        frame = self._card(parent, bg=bg, border=bg, padx=16, pady=14)
        tk.Label(
            frame,
            text=label.upper(),
            bg=bg,
            fg=accent,
            font=("Segoe UI Semibold", 9),
        ).pack(anchor="w")
        tk.Label(
            frame,
            textvariable=value_var,
            bg=bg,
            fg=self.colors["text"],
            font=("Segoe UI Semibold", 26),
        ).pack(anchor="w", pady=(6, 0))
        return frame

    def _text_panel(self, parent: tk.Misc, title: str, readonly: bool = True) -> tk.Text:
        shell = self._card(parent, bg=self.colors["panel"], border=self.colors["border"], padx=12, pady=12)
        self._field_label(shell, title).pack(anchor="w")
        text = tk.Text(
            shell,
            wrap="word",
            height=12,
            bg=self.colors["panel"],
            fg=self.colors["text"],
            bd=0,
            relief="flat",
            insertbackground=self.colors["text"],
            selectbackground=self.colors["hero_alt"],
            selectforeground=self.colors["white"],
            font=("Segoe UI", 10),
            padx=2,
            pady=6,
        )
        text.pack(fill="both", expand=True, pady=(8, 0))
        text._readonly = readonly  # type: ignore[attr-defined]
        if readonly:
            text.configure(state="disabled")
        return text

    def refresh_results(self, select_dedupe_key: str | None = None) -> None:
        with ListingStore(self.db_path) as store:
            payloads = store.list_listings(
                search=self.search_var.get(),
                fit_label=self.filter_var.get(),
                contacted_filter=self.contacted_filter_var.get(),
                interest_filter=self.interest_filter_var.get(),
                sort_by=self.sort_var.get(),
                limit=300,
            )

        self.tree.delete(*self.tree.get_children())
        self.listings_by_key.clear()
        listings: list[Listing] = []
        selected_item_id: str | None = None
        for index, payload in enumerate(payloads):
            listing = Listing(**payload)
            listings.append(listing)
            key = listing.dedupe_key or f"row-{index}"
            self.listings_by_key[key] = listing
            tags = [key]
            if listing.fit_label:
                tags.append(listing.fit_label)
            if listing.contacted:
                tags.append("contacted")
            if listing.not_interested:
                tags.append("not_interested")
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
                tags=tuple(tags),
            )
            if select_dedupe_key and key == select_dedupe_key:
                selected_item_id = item_id

        self._update_metrics(listings)
        self.results_meta_var.set(f"{len(listings)} listings shown from the local SQLite store.")
        self.controls_meta_var.set(
            f"Fit: {self.filter_var.get()} | Contacted: {self.contacted_filter_var.get()} | Interest: {self.interest_filter_var.get()} | Sort: {self.sort_var.get()} | Search: {self.search_var.get().strip() or 'none'}"
        )

        if payloads:
            first_item = selected_item_id or self.tree.get_children()[0]
            self.tree.selection_set(first_item)
            self._load_tree_item(first_item)
            self._set_status(f"Loaded {len(payloads)} listings", tone="blue")
        else:
            self.selected_listing = None
            self._clear_details()
            self._set_status("No listings match the current filter", tone="warm")

    def run_search(self) -> None:
        if self._search_thread and self._search_thread.is_alive():
            return
        self.run_button.configure(state="disabled")
        self._set_status("Running search...", tone="accent")
        self._search_thread = threading.Thread(target=self._run_search_worker, daemon=True)
        self._search_thread.start()

    def _run_search_worker(self) -> None:
        try:
            criteria = load_criteria(self.criteria_path)
            sources = load_sources(self.sources_path)
            browser_capture = self._build_browser_capture(sources)
            report = run_live(
                criteria=criteria,
                sources=sources,
                db_path=self.db_path,
                output_dir=self.output_dir,
                browser_capture=browser_capture,
            )
            self.after(0, lambda: self._on_search_complete(report, None))
        except Exception as exc:  # pragma: no cover - UI path
            self.after(0, lambda: self._on_search_complete(None, exc))

    def _on_search_complete(self, report: dict | None, error: Exception | None) -> None:
        self.run_button.configure(state="normal")
        if error is not None:
            self._set_status(f"Search failed: {error}", tone="danger")
            messagebox.showerror("Apartment Agent", f"Search failed:\n\n{error}")
            return

        self.refresh_results()
        if report is not None:
            error_count = len(report.get("errors", []))
            suffix = f" {error_count} source error(s)." if error_count else ""
            self._set_status(
                f"Search complete. {len(report['alerts'])} alerts, {len(report['watch'])} watch listings.{suffix}",
                tone="warm" if error_count else "accent",
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
        self._set_selection_badge(listing)
        self.meta_var.set(
            " | ".join(
                part
                for part in [
                    listing.project_name,
                    listing.site_name,
                    listing.fit_label.upper(),
                    f"Contacted {'Yes' if listing.contacted else 'No'}",
                    f"Hidden {'Yes' if listing.not_interested else 'No'}",
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
        self.notebook.select(self.email_tab)
        self._set_status("Draft regenerated and saved.", tone="accent")

    def copy_email(self) -> None:
        subject = self.subject_var.get().strip()
        body = self.email_body_text.get("1.0", "end").strip()
        if not subject and not body:
            return
        self._copy_to_clipboard(f"Subject: {subject}\n\n{body}")
        self._set_status("Email copied to clipboard.", tone="blue")

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
            self._set_status("Opened Gmail draft with recipient, subject, and body prefilled.", tone="blue")
        else:
            self._set_status(
                "Opened Gmail draft with subject and body prefilled. Recipient email is missing.",
                tone="warm",
            )

    def copy_agent_info(self) -> None:
        if not self.selected_listing:
            return
        self._copy_to_clipboard(_contact_block(self.selected_listing))
        self._set_status("Agent contact info copied to clipboard.", tone="blue")

    def set_contacted(self, contacted: bool) -> None:
        if not self.selected_listing:
            return
        with ListingStore(self.db_path) as store:
            store.set_contacted(self.selected_listing.dedupe_key, contacted)
        state_text = "contacted" if contacted else "not contacted"
        self._set_status(f"Marked listing as {state_text}.", tone="warm" if contacted else "neutral")
        self.refresh_results(select_dedupe_key=self.selected_listing.dedupe_key)

    def set_not_interested(self, not_interested: bool) -> None:
        if not self.selected_listing:
            return
        with ListingStore(self.db_path) as store:
            store.set_not_interested(self.selected_listing.dedupe_key, not_interested)
        if not_interested:
            self._set_status("Listing hidden as not interested.", tone="danger")
            self.refresh_results()
            return
        self._set_status("Listing restored to active results.", tone="blue")
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
        if getattr(widget, "_readonly", True):
            widget.configure(state="disabled")

    def _load_current_criteria(self):
        self.criteria = load_criteria(self.criteria_path)
        return self.criteria

    def _build_browser_capture(self, sources: list):
        requires_browser = any(getattr(source, "name", "").lower() == "hipflat" for source in sources)
        capture_conflicts = os.getenv("APARTMENT_AGENT_CAPTURE_CONFLICTS", "").strip().lower() in {"1", "true", "yes"}
        if not requires_browser and not capture_conflicts:
            return None
        try:
            from apartment_agent.browser import PlaywrightCapture
        except Exception:
            return None
        profile_dir = os.getenv("APARTMENT_AGENT_BROWSER_PROFILE_DIR")
        headful = os.getenv("APARTMENT_AGENT_BROWSER_HEADFUL", "").strip().lower() in {"1", "true", "yes"}
        return PlaywrightCapture(
            headless=not headful,
            user_data_dir=profile_dir or None,
            wait_seconds=float(os.getenv("APARTMENT_AGENT_BROWSER_WAIT_SECONDS", "2.0")),
        )

    def _clear_details(self) -> None:
        self.title_var.set("No listing selected")
        self.meta_var.set("")
        self._set_selection_badge(None)
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
        f"Not Interested: {'Yes' if listing.not_interested else 'No'}",
        f"Hidden At: {listing.not_interested_at or '-'}",
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
