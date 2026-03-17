from __future__ import annotations

import os
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, simpledialog, ttk
from urllib.parse import urlencode

from apartment_agent.agent_research import (
    build_agent_research_query,
    build_agent_search_url,
    collect_research_emails,
    research_agent,
)
from apartment_agent.config import load_criteria, load_sources
from apartment_agent.email_drafts import build_email_draft
from apartment_agent.mailer import (
    SMTPConfigurationError,
    SMTPSettings,
    apply_env_overrides,
    get_smtp_env_values,
    load_smtp_settings_from_env,
    save_smtp_env_values,
    send_email,
    test_smtp_connection,
)
from apartment_agent.models import EmailDraft, Listing
from apartment_agent.pipeline import run_live
from apartment_agent.storage import ListingStore
from apartment_agent.utils import utc_now_iso


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
        self.env_path = os.path.abspath(".env")
        apply_env_overrides(self.env_path)
        self.criteria = load_criteria(criteria_path)
        self.selected_listing: Listing | None = None
        self.listings_by_key: dict[str, Listing] = {}
        self._search_thread: threading.Thread | None = None
        self._research_thread: threading.Thread | None = None
        self._email_thread: threading.Thread | None = None
        self._smtp_thread: threading.Thread | None = None
        self._email_lookup_thread: threading.Thread | None = None
        self.current_agent_research: dict | None = None
        self.tree_sort_column = ""
        self.tree_sort_descending = False
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
        self.tree_columns = ("fit", "viewed", "emailed", "contacted", "listed", "score", "price", "size", "site", "project")
        self.tree_labels = {
            "fit": "Fit",
            "viewed": "Viewed",
            "emailed": "Emailed",
            "contacted": "Contacted",
            "listed": "Listed",
            "score": "Score",
            "price": "Rent",
            "size": "Sqm",
            "site": "Site",
            "project": "Project / Title",
        }
        self.tree = ttk.Treeview(tree_shell, columns=self.tree_columns, show="headings", selectmode="browse")
        for column, width in [("fit", 78), ("viewed", 78), ("emailed", 84), ("contacted", 92), ("listed", 108), ("score", 72), ("price", 110), ("size", 70), ("site", 92), ("project", 320)]:
            self.tree.heading(column, text=self.tree_labels[column], command=lambda selected=column: self.on_tree_heading_click(selected))
            self.tree.column(column, width=width, anchor="w")
        self.tree.tag_configure("alert", background="#EAF8F5")
        self.tree.tag_configure("watch", background="#FFF7EB")
        self.tree.tag_configure("reject", foreground="#8892A0")
        self.tree.tag_configure("viewed", foreground="#455468")
        self.tree.tag_configure("emailed", foreground="#365314")
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
        self.send_email_button = ttk.Button(primary_actions, text="Send Email", style="Accent.TButton", command=self.send_email_direct)
        self.send_email_button.pack(side="left", padx=(8, 0))
        self.regenerate_draft_button = ttk.Button(primary_actions, text="Regenerate Draft", style="Accent.TButton", command=self.regenerate_draft)
        self.regenerate_draft_button.pack(side="left", padx=(8, 0))
        self.copy_email_button = ttk.Button(primary_actions, text="Copy Email", style="Ghost.TButton", command=self.copy_email)
        self.copy_email_button.pack(side="left", padx=(8, 0))

        secondary_actions = tk.Frame(action_card, bg=self.colors["panel"])
        secondary_actions.pack(fill="x", pady=(10, 0))
        ttk.Button(secondary_actions, text="Mark Viewed", style="Ghost.TButton", command=lambda: self.set_viewed(True)).pack(side="left")
        ttk.Button(secondary_actions, text="Mark Not Viewed", style="Ghost.TButton", command=lambda: self.set_viewed(False)).pack(side="left", padx=(8, 0))
        ttk.Button(secondary_actions, text="Mark Emailed", style="Ghost.TButton", command=lambda: self.set_emailed(True)).pack(side="left", padx=(8, 0))
        ttk.Button(secondary_actions, text="Mark Not Emailed", style="Ghost.TButton", command=lambda: self.set_emailed(False)).pack(side="left", padx=(8, 0))
        ttk.Button(secondary_actions, text="Mark Contacted", style="Warm.TButton", command=lambda: self.set_contacted(True)).pack(side="left", padx=(8, 0))
        ttk.Button(secondary_actions, text="Mark Not Contacted", style="Ghost.TButton", command=lambda: self.set_contacted(False)).pack(side="left", padx=(8, 0))

        tertiary_actions = tk.Frame(action_card, bg=self.colors["panel"])
        tertiary_actions.pack(fill="x", pady=(10, 0))
        self.hide_listing_button = ttk.Button(tertiary_actions, text="Hide Listing", style="Danger.TButton", command=lambda: self.set_not_interested(True))
        self.hide_listing_button.pack(side="left")
        self.restore_listing_button = ttk.Button(tertiary_actions, text="Restore Listing", style="Ghost.TButton", command=lambda: self.set_not_interested(False))
        self.restore_listing_button.pack(side="left", padx=(8, 0))
        ttk.Button(tertiary_actions, text="Copy Agent Info", style="Ghost.TButton", command=self.copy_agent_info).pack(side="left", padx=(8, 0))

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
        self.email_tab.rowconfigure(4, weight=1)
        self._field_label(self.email_tab, "Recipient Email").grid(row=0, column=0, sticky="w")
        recipient_row = tk.Frame(self.email_tab, bg=self.colors["card"])
        recipient_row.grid(row=1, column=0, sticky="ew", pady=(6, 10))
        recipient_row.columnconfigure(0, weight=1)
        self.recipient_email_var = tk.StringVar()
        self.recipient_entry = ttk.Entry(recipient_row, textvariable=self.recipient_email_var, style="Search.TEntry")
        self.recipient_entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(recipient_row, text="Save Recipient", style="Ghost.TButton", command=self.save_contact_email).grid(row=0, column=1, padx=(8, 0))
        self.find_email_button = ttk.Button(recipient_row, text="Find / Set Email", style="Blue.TButton", command=self.find_or_set_contact_email)
        self.find_email_button.grid(row=0, column=2, padx=(8, 0))
        self._field_label(self.email_tab, "Email Subject").grid(row=2, column=0, sticky="w")
        self.subject_var = tk.StringVar()
        self.subject_entry = ttk.Entry(self.email_tab, textvariable=self.subject_var, style="Search.TEntry")
        self.subject_entry.grid(row=3, column=0, sticky="ew", pady=(6, 10))
        self.email_body_text = self._text_panel(self.email_tab, "Email Body", readonly=False)
        self.email_body_text.master.grid(row=4, column=0, sticky="nsew")
        self.notebook.add(self.email_tab, text="Email Draft")

        self.research_tab = tk.Frame(self.notebook, bg=self.colors["card"])
        self.research_tab.columnconfigure(0, weight=3)
        self.research_tab.columnconfigure(1, weight=2)
        self.research_tab.rowconfigure(3, weight=1)

        research_header = tk.Frame(self.research_tab, bg=self.colors["card"])
        research_header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        research_header.columnconfigure(0, weight=1)
        self._field_label(research_header, "Agent Research").grid(row=0, column=0, sticky="w")
        self.research_meta_var = tk.StringVar(value="No cached research yet.")
        tk.Label(
            research_header,
            textvariable=self.research_meta_var,
            bg=self.colors["card"],
            fg=self.colors["muted"],
            font=("Segoe UI", 10),
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        research_actions = tk.Frame(research_header, bg=self.colors["card"])
        research_actions.grid(row=0, column=1, rowspan=2, sticky="e")
        self.research_button = ttk.Button(research_actions, text="Research Agent / Company", style="Accent.TButton", command=self.refresh_agent_research)
        self.research_button.pack(side="left")
        self.open_research_search_button = ttk.Button(research_actions, text="Open Research Search", style="Ghost.TButton", command=self.open_agent_research_search)
        self.open_research_search_button.pack(side="left", padx=(8, 0))
        self.open_research_source_button = ttk.Button(research_actions, text="Open Top Result", style="Ghost.TButton", command=self.open_agent_research_top_source)
        self.open_research_source_button.pack(side="left", padx=(8, 0))

        self._field_label(self.research_tab, "Research Query").grid(row=1, column=0, columnspan=2, sticky="w")
        self.research_query_var = tk.StringVar(value="")
        self.research_query_entry = ttk.Entry(self.research_tab, textvariable=self.research_query_var, style="Search.TEntry")
        self.research_query_entry.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 10))

        self.research_summary_text = self._text_panel(self.research_tab, "Research Summary")
        self.research_summary_text.master.grid(row=3, column=0, sticky="nsew", padx=(0, 10))
        self.research_sources_text = self._text_panel(self.research_tab, "Web Sources")
        self.research_sources_text.master.grid(row=3, column=1, sticky="nsew")
        self.notebook.add(self.research_tab, text="Research")

        self.settings_tab = tk.Frame(self.notebook, bg=self.colors["card"])
        self.settings_tab.columnconfigure(0, weight=1)
        self.settings_tab.columnconfigure(1, weight=1)

        self.smtp_host_var = tk.StringVar()
        self.smtp_port_var = tk.StringVar()
        self.smtp_username_var = tk.StringVar()
        self.smtp_password_var = tk.StringVar()
        self.smtp_from_var = tk.StringVar()
        self.smtp_from_name_var = tk.StringVar()
        self.smtp_reply_to_var = tk.StringVar()
        self.smtp_use_tls_var = tk.BooleanVar(value=True)
        self.smtp_settings_meta_var = tk.StringVar(
            value="Stored in local .env only. Use a Gmail app password here, not your main Google account password."
        )

        settings_header = tk.Frame(self.settings_tab, bg=self.colors["card"])
        settings_header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        settings_header.columnconfigure(0, weight=1)
        self._field_label(settings_header, "Direct Email Settings").grid(row=0, column=0, sticky="w")
        tk.Label(
            settings_header,
            textvariable=self.smtp_settings_meta_var,
            bg=self.colors["card"],
            fg=self.colors["muted"],
            font=("Segoe UI", 10),
            justify="left",
            wraplength=760,
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        settings_actions = tk.Frame(settings_header, bg=self.colors["card"])
        settings_actions.grid(row=0, column=1, rowspan=2, sticky="e")
        ttk.Button(settings_actions, text="Use Gmail Defaults", style="Ghost.TButton", command=self.use_gmail_defaults).pack(side="left")
        ttk.Button(settings_actions, text="Reload .env", style="Ghost.TButton", command=self.reload_smtp_settings).pack(side="left", padx=(8, 0))
        self.test_smtp_button = ttk.Button(settings_actions, text="Test SMTP", style="Blue.TButton", command=self.test_smtp_settings)
        self.test_smtp_button.pack(side="left", padx=(8, 0))
        ttk.Button(settings_actions, text="Save Settings", style="Accent.TButton", command=self.save_smtp_settings).pack(side="left", padx=(8, 0))

        self._field_label(self.settings_tab, "SMTP Host").grid(row=1, column=0, sticky="w")
        ttk.Entry(self.settings_tab, textvariable=self.smtp_host_var, style="Search.TEntry").grid(row=2, column=0, sticky="ew", pady=(6, 10), padx=(0, 10))
        self._field_label(self.settings_tab, "Port").grid(row=1, column=1, sticky="w")
        ttk.Entry(self.settings_tab, textvariable=self.smtp_port_var, style="Search.TEntry").grid(row=2, column=1, sticky="ew", pady=(6, 10))

        self._field_label(self.settings_tab, "SMTP Username").grid(row=3, column=0, sticky="w")
        ttk.Entry(self.settings_tab, textvariable=self.smtp_username_var, style="Search.TEntry").grid(row=4, column=0, sticky="ew", pady=(6, 10), padx=(0, 10))
        self._field_label(self.settings_tab, "SMTP Password / App Password").grid(row=3, column=1, sticky="w")
        ttk.Entry(self.settings_tab, textvariable=self.smtp_password_var, style="Search.TEntry", show="*").grid(row=4, column=1, sticky="ew", pady=(6, 10))

        self._field_label(self.settings_tab, "From Email").grid(row=5, column=0, sticky="w")
        ttk.Entry(self.settings_tab, textvariable=self.smtp_from_var, style="Search.TEntry").grid(row=6, column=0, sticky="ew", pady=(6, 10), padx=(0, 10))
        self._field_label(self.settings_tab, "From Name").grid(row=5, column=1, sticky="w")
        ttk.Entry(self.settings_tab, textvariable=self.smtp_from_name_var, style="Search.TEntry").grid(row=6, column=1, sticky="ew", pady=(6, 10))

        self._field_label(self.settings_tab, "Reply-To").grid(row=7, column=0, sticky="w")
        ttk.Entry(self.settings_tab, textvariable=self.smtp_reply_to_var, style="Search.TEntry").grid(row=8, column=0, sticky="ew", pady=(6, 10), padx=(0, 10))
        ttk.Checkbutton(self.settings_tab, text="Use TLS", variable=self.smtp_use_tls_var).grid(row=8, column=1, sticky="w", pady=(6, 10))

        self.smtp_path_var = tk.StringVar(value=os.path.abspath(self.env_path))
        tk.Label(
            self.settings_tab,
            textvariable=self.smtp_path_var,
            bg=self.colors["panel"],
            fg=self.colors["muted"],
            font=("Consolas", 9),
            anchor="w",
            padx=10,
            pady=8,
        ).grid(row=9, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        self.notebook.add(self.settings_tab, text="Settings")
        self.reload_smtp_settings()

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

    def on_tree_heading_click(self, column: str) -> None:
        if self.tree_sort_column == column:
            self.tree_sort_descending = not self.tree_sort_descending
        else:
            self.tree_sort_column = column
            self.tree_sort_descending = column not in {"project", "site", "fit"}
        self.refresh_results(select_dedupe_key=self.selected_listing.dedupe_key if self.selected_listing else None)

    def _apply_tree_heading_labels(self) -> None:
        for column in self.tree_columns:
            label = self.tree_labels[column]
            if column == self.tree_sort_column:
                label = f"{label} {'▼' if self.tree_sort_descending else '▲'}"
            self.tree.heading(column, text=label, command=lambda selected=column: self.on_tree_heading_click(selected))

    def _sort_listings_for_display(self, listings: list[Listing]) -> list[Listing]:
        if not self.tree_sort_column:
            return listings

        def sort_key(listing: Listing):
            if self.tree_sort_column == "fit":
                order = {"alert": 0, "watch": 1, "reject": 2}
                return (order.get(listing.fit_label, 9), listing.project_name or listing.title or "")
            if self.tree_sort_column == "viewed":
                return (0 if listing.viewed else 1, listing.viewed_at or "")
            if self.tree_sort_column == "emailed":
                return (0 if listing.emailed else 1, listing.emailed_at or "")
            if self.tree_sort_column == "contacted":
                return (0 if listing.contacted else 1, listing.contacted_at or "")
            if self.tree_sort_column == "listed":
                return listing.listing_date or ""
            if self.tree_sort_column == "score":
                return listing.match_score
            if self.tree_sort_column == "price":
                return listing.price_baht if listing.price_baht is not None else -1
            if self.tree_sort_column == "size":
                return listing.size_sqm if listing.size_sqm is not None else -1
            if self.tree_sort_column == "site":
                return listing.site_name or ""
            return (listing.project_name or listing.title or "").lower()

        return sorted(listings, key=sort_key, reverse=self.tree_sort_descending)

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
        listings = self._sort_listings_for_display([Listing(**payload) for payload in payloads])
        self._apply_tree_heading_labels()
        selected_item_id: str | None = None
        for index, listing in enumerate(listings):
            key = listing.dedupe_key or f"row-{index}"
            self.listings_by_key[key] = listing
            tags = [key]
            if listing.fit_label:
                tags.append(listing.fit_label)
            if listing.viewed:
                tags.append("viewed")
            if listing.emailed:
                tags.append("emailed")
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
                    "Yes" if listing.viewed else "No",
                    "Yes" if listing.emailed else "No",
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
            f"Fit: {self.filter_var.get()} | Contacted: {self.contacted_filter_var.get()} | Interest: {self.interest_filter_var.get()} | Sort: {self.sort_var.get()} | Header sort: {self.tree_sort_column or 'none'} | Search: {self.search_var.get().strip() or 'none'}"
        )

        if listings:
            first_item = selected_item_id or self.tree.get_children()[0]
            self.tree.selection_set(first_item)
            self._load_tree_item(first_item)
            self._set_status(f"Loaded {len(listings)} listings", tone="blue")
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
                    f"Viewed {'Yes' if listing.viewed else 'No'}",
                    f"Emailed {'Yes' if listing.emailed else 'No'}",
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
        self.recipient_email_var.set(listing.contact_email or "")

        with ListingStore(self.db_path) as store:
            stored_draft = store.get_latest_email_draft(listing.dedupe_key)
            stored_research = store.get_agent_research(listing.dedupe_key)

        if stored_draft:
            self.subject_var.set(stored_draft["subject"])
            self._set_text(self.email_body_text, stored_draft["body"])
        else:
            draft = build_email_draft(listing, self._load_current_criteria())
            self.subject_var.set(draft.subject)
            self._set_text(self.email_body_text, draft.body)

        self._display_agent_research(listing, stored_research)

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

    def refresh_agent_research(self) -> None:
        if not self.selected_listing:
            return
        if self._research_thread and self._research_thread.is_alive():
            return

        listing = self.selected_listing
        self.research_button.configure(state="disabled")
        self.research_meta_var.set("Running live web research for this agent/company...")
        self._set_text(self.research_summary_text, "Researching the web for company and agent context...")
        self._set_text(self.research_sources_text, "")
        self._set_status("Researching agent/company...", tone="accent")
        self._research_thread = threading.Thread(target=self._run_agent_research_worker, args=(listing,), daemon=True)
        self._research_thread.start()

    def _run_agent_research_worker(self, listing: Listing) -> None:
        try:
            payload = research_agent(listing).to_dict()
            with ListingStore(self.db_path) as store:
                store.store_agent_research(listing.dedupe_key, payload)
            self.after(0, lambda: self._on_agent_research_complete(listing.dedupe_key, payload, None))
        except Exception as exc:  # pragma: no cover - UI path
            self.after(0, lambda: self._on_agent_research_complete(listing.dedupe_key, None, exc))

    def _on_agent_research_complete(
        self,
        dedupe_key: str,
        payload: dict | None,
        error: Exception | None,
    ) -> None:
        self.research_button.configure(state="normal")
        if error is not None:
            self.research_meta_var.set(f"Research failed: {error}")
            self._set_status(f"Research failed: {error}", tone="danger")
            return
        if payload is None:
            return

        if self.selected_listing and self.selected_listing.dedupe_key == dedupe_key:
            self._display_agent_research(self.selected_listing, payload)
            self.notebook.select(self.research_tab)
        self._set_status("Agent/company research refreshed.", tone="blue")

    def copy_email(self) -> None:
        subject = self.subject_var.get().strip()
        body = self.email_body_text.get("1.0", "end").strip()
        if not subject and not body:
            return
        self._copy_to_clipboard(f"Subject: {subject}\n\n{body}")
        self._set_status("Email copied to clipboard.", tone="blue")

    def save_contact_email(self) -> bool:
        if not self.selected_listing:
            return False
        value = self.recipient_email_var.get().strip().lower()
        if value and "@" not in value:
            messagebox.showerror("Apartment Agent", "Recipient email must look like a valid email address.")
            return False
        with ListingStore(self.db_path) as store:
            store.update_contact_email(self.selected_listing.dedupe_key, value or None)
        self._set_status("Saved recipient email for this listing.", tone="blue")
        self.refresh_results(select_dedupe_key=self.selected_listing.dedupe_key)
        return True

    def find_or_set_contact_email(self, prompt_if_missing: bool = False) -> bool:
        if not self.selected_listing:
            return False
        candidates = collect_research_emails(self.current_agent_research)
        if candidates:
            return self._prompt_for_contact_email(candidates)
        if self._email_lookup_thread and self._email_lookup_thread.is_alive():
            return False
        self.find_email_button.configure(state="disabled")
        self._set_status("Looking up a contact email from web research...", tone="accent")
        listing = self.selected_listing
        self._email_lookup_thread = threading.Thread(
            target=self._run_contact_email_lookup_worker,
            args=(listing, prompt_if_missing),
            daemon=True,
        )
        self._email_lookup_thread.start()
        return False

    def _run_contact_email_lookup_worker(self, listing: Listing, prompt_if_missing: bool) -> None:
        try:
            payload = research_agent(listing).to_dict()
            with ListingStore(self.db_path) as store:
                store.store_agent_research(listing.dedupe_key, payload)
            candidates = collect_research_emails(payload)
            self.after(0, lambda: self._on_contact_email_lookup_complete(listing.dedupe_key, payload, candidates, prompt_if_missing, None))
        except Exception as exc:  # pragma: no cover - UI path
            self.after(0, lambda: self._on_contact_email_lookup_complete(listing.dedupe_key, None, [], prompt_if_missing, exc))

    def _on_contact_email_lookup_complete(
        self,
        dedupe_key: str,
        payload: dict | None,
        candidates: list[str],
        prompt_if_missing: bool,
        error: Exception | None,
    ) -> None:
        self.find_email_button.configure(state="normal")
        if error is not None:
            self._set_status(f"Email lookup failed: {error}", tone="danger")
            if prompt_if_missing:
                self._prompt_for_contact_email([])
            else:
                messagebox.showerror("Apartment Agent", f"Could not research an agent email:\n\n{error}")
            return
        if self.selected_listing and self.selected_listing.dedupe_key == dedupe_key and payload is not None:
            self._display_agent_research(self.selected_listing, payload)
        if candidates:
            self._set_status("Email candidates found from agent/company research.", tone="blue")
            saved = self._prompt_for_contact_email(candidates)
            if prompt_if_missing and saved:
                self._set_status("Saved the agent email. Click Gmail or Send Email again to continue.", tone="blue")
            return
        if prompt_if_missing:
            saved = self._prompt_for_contact_email([])
            if saved:
                self._set_status("Saved the agent email. Click Gmail or Send Email again to continue.", tone="blue")
            return
        self._set_status("No email candidates found from research. Add one manually if needed.", tone="warm")

    def _prompt_for_contact_email(self, candidates: list[str]) -> bool:
        if not self.selected_listing:
            return False
        candidate_lines = candidates[:5]
        prompt_lines = [
            "Set the agent email for this listing.",
        ]
        if candidate_lines:
            prompt_lines.extend(
                [
                    "",
                    "Research candidates:",
                    *[f"- {email}" for email in candidate_lines],
                    "",
                    "Edit the email below or accept one of the candidates.",
                ]
            )
        else:
            prompt_lines.extend(
                [
                    "",
                    "No candidate email was found automatically.",
                    "Enter the correct email manually.",
                ]
            )
        initial_value = self.recipient_email_var.get().strip() or (candidate_lines[0] if candidate_lines else "")
        selected = simpledialog.askstring(
            "Set Agent Email",
            "\n".join(prompt_lines),
            initialvalue=initial_value,
            parent=self,
        )
        if selected is None:
            return False
        self.recipient_email_var.set(selected.strip().lower())
        return self.save_contact_email()

    def use_gmail_defaults(self) -> None:
        defaults = {
            "APARTMENT_AGENT_SMTP_HOST": "smtp.gmail.com",
            "APARTMENT_AGENT_SMTP_PORT": "587",
            "APARTMENT_AGENT_SMTP_USERNAME": "pzgambo@gmail.com",
            "APARTMENT_AGENT_SMTP_PASSWORD": "",
            "APARTMENT_AGENT_SMTP_FROM": "pzgambo@gmail.com",
            "APARTMENT_AGENT_SMTP_FROM_NAME": self.criteria.sender_name or "Patrick",
            "APARTMENT_AGENT_SMTP_REPLY_TO": "pzgambo@gmail.com",
            "APARTMENT_AGENT_SMTP_USE_TLS": "1",
        }
        self._apply_smtp_values(defaults)
        self.smtp_settings_meta_var.set(
            "Gmail defaults loaded. Add a Gmail app password, then click Save Settings."
        )
        self._set_status("Loaded Gmail defaults into the settings form.", tone="blue")
        self.notebook.select(self.settings_tab)

    def reload_smtp_settings(self) -> None:
        apply_env_overrides(self.env_path)
        values = get_smtp_env_values(self.env_path)
        self._apply_smtp_values(values)
        self.smtp_settings_meta_var.set(
            "Loaded SMTP settings from local .env. This file is intended to stay out of git."
        )

    def save_smtp_settings(self) -> None:
        values = {
            "APARTMENT_AGENT_SMTP_HOST": self.smtp_host_var.get().strip(),
            "APARTMENT_AGENT_SMTP_PORT": self.smtp_port_var.get().strip(),
            "APARTMENT_AGENT_SMTP_USERNAME": self.smtp_username_var.get().strip(),
            "APARTMENT_AGENT_SMTP_PASSWORD": self.smtp_password_var.get(),
            "APARTMENT_AGENT_SMTP_FROM": self.smtp_from_var.get().strip(),
            "APARTMENT_AGENT_SMTP_FROM_NAME": self.smtp_from_name_var.get().strip(),
            "APARTMENT_AGENT_SMTP_REPLY_TO": self.smtp_reply_to_var.get().strip(),
            "APARTMENT_AGENT_SMTP_USE_TLS": "1" if self.smtp_use_tls_var.get() else "0",
        }
        if not values["APARTMENT_AGENT_SMTP_FROM"] and values["APARTMENT_AGENT_SMTP_USERNAME"]:
            values["APARTMENT_AGENT_SMTP_FROM"] = values["APARTMENT_AGENT_SMTP_USERNAME"]
        if not values["APARTMENT_AGENT_SMTP_REPLY_TO"] and values["APARTMENT_AGENT_SMTP_FROM"]:
            values["APARTMENT_AGENT_SMTP_REPLY_TO"] = values["APARTMENT_AGENT_SMTP_FROM"]
        save_smtp_env_values(values, self.env_path)
        self.smtp_settings_meta_var.set(
            "Saved SMTP settings to local .env. Direct send will use this profile."
        )
        self._set_status("Saved local SMTP settings.", tone="accent")

    def test_smtp_settings(self) -> None:
        if self._smtp_thread and self._smtp_thread.is_alive():
            return
        try:
            settings = self._build_smtp_settings_from_form()
        except SMTPConfigurationError as exc:
            messagebox.showerror("Apartment Agent", str(exc))
            return
        self.test_smtp_button.configure(state="disabled")
        self._set_status("Testing SMTP connection...", tone="accent")
        self._smtp_thread = threading.Thread(target=self._run_smtp_test_worker, args=(settings,), daemon=True)
        self._smtp_thread.start()

    def _build_smtp_settings_from_form(self) -> SMTPSettings:
        host = self.smtp_host_var.get().strip()
        port_text = self.smtp_port_var.get().strip() or "587"
        username = self.smtp_username_var.get().strip()
        password = self.smtp_password_var.get()
        from_email = (self.smtp_from_var.get().strip() or username)
        reply_to = self.smtp_reply_to_var.get().strip() or from_email
        from_name = self.smtp_from_name_var.get().strip()
        missing = [
            name
            for name, value in [
                ("SMTP host", host),
                ("SMTP username", username),
                ("SMTP password / app password", password),
                ("From email", from_email),
            ]
            if not value
        ]
        if missing:
            raise SMTPConfigurationError("Missing settings: " + ", ".join(missing))
        try:
            port = int(port_text)
        except ValueError as exc:
            raise SMTPConfigurationError("SMTP port must be an integer.") from exc
        return SMTPSettings(
            host=host,
            port=port,
            username=username,
            password=password,
            from_email=from_email,
            from_name=from_name,
            reply_to=reply_to,
            use_tls=self.smtp_use_tls_var.get(),
        )

    def _run_smtp_test_worker(self, settings: SMTPSettings) -> None:
        try:
            test_smtp_connection(settings)
            self.after(0, lambda: self._on_smtp_test_complete(None))
        except Exception as exc:  # pragma: no cover - UI path
            self.after(0, lambda: self._on_smtp_test_complete(exc))

    def _on_smtp_test_complete(self, error: Exception | None) -> None:
        self.test_smtp_button.configure(state="normal")
        if error is not None:
            self._set_status(f"SMTP test failed: {error}", tone="danger")
            messagebox.showerror("Apartment Agent", f"SMTP test failed:\n\n{error}")
            return
        self._set_status("SMTP connection succeeded.", tone="blue")
        messagebox.showinfo("Apartment Agent", "SMTP connection succeeded.")

    def _apply_smtp_values(self, values: dict[str, str]) -> None:
        self.smtp_host_var.set(values.get("APARTMENT_AGENT_SMTP_HOST", ""))
        self.smtp_port_var.set(values.get("APARTMENT_AGENT_SMTP_PORT", ""))
        self.smtp_username_var.set(values.get("APARTMENT_AGENT_SMTP_USERNAME", ""))
        self.smtp_password_var.set(values.get("APARTMENT_AGENT_SMTP_PASSWORD", ""))
        self.smtp_from_var.set(values.get("APARTMENT_AGENT_SMTP_FROM", ""))
        self.smtp_from_name_var.set(values.get("APARTMENT_AGENT_SMTP_FROM_NAME", ""))
        self.smtp_reply_to_var.set(values.get("APARTMENT_AGENT_SMTP_REPLY_TO", ""))
        self.smtp_use_tls_var.set(values.get("APARTMENT_AGENT_SMTP_USE_TLS", "1").strip().lower() not in {"0", "false", "no"})

    def send_email_direct(self) -> None:
        if not self.selected_listing:
            return
        if self._email_thread and self._email_thread.is_alive():
            return

        recipient = self.recipient_email_var.get().strip().lower()
        if not recipient:
            if not self.find_or_set_contact_email(prompt_if_missing=True):
                return
            recipient = self.recipient_email_var.get().strip().lower()
            if not recipient:
                return
        elif recipient != (self.selected_listing.contact_email or "").strip().lower():
            if not self.save_contact_email():
                return

        subject = self.subject_var.get().strip()
        body = self.email_body_text.get("1.0", "end").strip()
        if not subject and not body:
            self.regenerate_draft()
            subject = self.subject_var.get().strip()
            body = self.email_body_text.get("1.0", "end").strip()

        try:
            settings = load_smtp_settings_from_env(self.env_path)
        except SMTPConfigurationError as exc:
            messagebox.showerror(
                "Apartment Agent",
                "\n".join(
                    [
                        str(exc),
                        "",
                        "Configure SMTP in the Settings tab or set these environment variables:",
                        "APARTMENT_AGENT_SMTP_HOST",
                        "APARTMENT_AGENT_SMTP_PORT",
                        "APARTMENT_AGENT_SMTP_USERNAME",
                        "APARTMENT_AGENT_SMTP_PASSWORD",
                        "APARTMENT_AGENT_SMTP_FROM",
                        "Optional: APARTMENT_AGENT_SMTP_FROM_NAME, APARTMENT_AGENT_SMTP_REPLY_TO, APARTMENT_AGENT_SMTP_USE_TLS",
                        "",
                        "For Gmail, use an app password here rather than your normal account password.",
                    ]
                ),
            )
            return

        self.send_email_button.configure(state="disabled")
        self._set_status(f"Sending email to {recipient}...", tone="accent")
        listing = self.selected_listing
        self._email_thread = threading.Thread(
            target=self._send_email_worker,
            args=(listing.dedupe_key, recipient, subject, body, settings),
            daemon=True,
        )
        self._email_thread.start()

    def _send_email_worker(
        self,
        dedupe_key: str,
        recipient: str,
        subject: str,
        body: str,
        settings,
    ) -> None:
        try:
            send_email(settings, recipient, subject, body)
            draft = EmailDraft(
                listing_dedupe_key=dedupe_key,
                subject=subject,
                body=body,
                created_at=utc_now_iso(),
            )
            with ListingStore(self.db_path) as store:
                store.store_email_draft(draft)
                store.set_emailed(dedupe_key, True)
                store.set_contacted(dedupe_key, True)
            self.after(0, lambda: self._on_send_email_complete(dedupe_key, recipient, None))
        except Exception as exc:  # pragma: no cover - UI path
            self.after(0, lambda: self._on_send_email_complete(dedupe_key, recipient, exc))

    def _on_send_email_complete(
        self,
        dedupe_key: str,
        recipient: str,
        error: Exception | None,
    ) -> None:
        self.send_email_button.configure(state="normal")
        if error is not None:
            self._set_status(f"Direct send failed: {error}", tone="danger")
            messagebox.showerror("Apartment Agent", f"Could not send the email directly:\n\n{error}")
            return

        self.refresh_results(select_dedupe_key=dedupe_key)
        self._set_status(f"Email sent directly to {recipient}. Listing marked as contacted.", tone="blue")

    def open_gmail_draft(self) -> None:
        if not self.selected_listing:
            return
        recipient = self.recipient_email_var.get().strip().lower()
        if not recipient:
            if not self.find_or_set_contact_email(prompt_if_missing=True):
                return
            recipient = self.recipient_email_var.get().strip().lower()
            if not recipient:
                return
        elif recipient != (self.selected_listing.contact_email or "").strip().lower():
            if not self.save_contact_email():
                return

        subject = self.subject_var.get().strip()
        body = self.email_body_text.get("1.0", "end").strip()
        if not subject and not body:
            self.regenerate_draft()
            subject = self.subject_var.get().strip()
            body = self.email_body_text.get("1.0", "end").strip()

        gmail_url = build_gmail_compose_url(
            to=recipient,
            subject=subject,
            body=body,
        )
        webbrowser.open(gmail_url)
        with ListingStore(self.db_path) as store:
            store.set_emailed(self.selected_listing.dedupe_key, True)
        self.refresh_results(select_dedupe_key=self.selected_listing.dedupe_key)

        self._set_status("Opened Gmail draft and marked the listing as emailed.", tone="blue")

    def copy_agent_info(self) -> None:
        if not self.selected_listing:
            return
        self._copy_to_clipboard(_contact_block(self.selected_listing))
        self._set_status("Agent contact info copied to clipboard.", tone="blue")

    def open_agent_research_search(self) -> None:
        if not self.selected_listing:
            return
        webbrowser.open(build_agent_search_url(self.selected_listing))
        self._set_status("Opened research search in the browser.", tone="blue")

    def open_agent_research_top_source(self) -> None:
        if self.current_agent_research:
            preferred_url = (
                self.current_agent_research.get("official_site_url")
                or self.current_agent_research.get("best_source_url")
            )
            if preferred_url:
                webbrowser.open(preferred_url)
                self._set_status("Opened top research result in the browser.", tone="blue")
                return
            if self.current_agent_research.get("sources"):
                top_source = self.current_agent_research["sources"][0]
                url = top_source.get("url")
                if url:
                    webbrowser.open(url)
                    self._set_status("Opened top research result in the browser.", tone="blue")
                    return
        self.open_agent_research_search()

    def set_contacted(self, contacted: bool) -> None:
        if not self.selected_listing:
            return
        with ListingStore(self.db_path) as store:
            store.set_contacted(self.selected_listing.dedupe_key, contacted)
        state_text = "contacted" if contacted else "not contacted"
        self._set_status(f"Marked listing as {state_text}.", tone="warm" if contacted else "neutral")
        self.refresh_results(select_dedupe_key=self.selected_listing.dedupe_key)

    def set_viewed(self, viewed: bool) -> None:
        if not self.selected_listing:
            return
        with ListingStore(self.db_path) as store:
            store.set_viewed(self.selected_listing.dedupe_key, viewed)
        self._set_status(f"Marked listing as {'viewed' if viewed else 'not viewed'}.", tone="blue" if viewed else "neutral")
        self.refresh_results(select_dedupe_key=self.selected_listing.dedupe_key)

    def set_emailed(self, emailed: bool) -> None:
        if not self.selected_listing:
            return
        with ListingStore(self.db_path) as store:
            store.set_emailed(self.selected_listing.dedupe_key, emailed)
        self._set_status(f"Marked listing as {'emailed' if emailed else 'not emailed'}.", tone="blue" if emailed else "neutral")
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
        with ListingStore(self.db_path) as store:
            store.set_viewed(self.selected_listing.dedupe_key, True)
        webbrowser.open(self.selected_listing.url)
        self.refresh_results(select_dedupe_key=self.selected_listing.dedupe_key)

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

    def _display_agent_research(self, listing: Listing, payload: dict | None) -> None:
        self.current_agent_research = payload
        self.research_query_var.set(str(payload.get("query")) if payload else build_agent_research_query(listing))

        if payload:
            researched_at = str(payload.get("researched_at") or "")[:19].replace("T", " ")
            confidence_score = payload.get("confidence_score")
            confidence_label = payload.get("confidence_label") or "unknown"
            official_domain = payload.get("official_site_domain") or "-"
            self.research_meta_var.set(
                f"Confidence: {confidence_score if confidence_score is not None else '-'} ({confidence_label}) | Official site: {official_domain} | Last refreshed: {researched_at or '-'}"
            )
            self._set_text(self.research_summary_text, str(payload.get("summary") or "No summary stored."))
            self._set_text(
                self.research_sources_text,
                _research_sources_block(
                    payload.get("sources", []),
                    payload.get("social_profiles", []),
                    payload.get("verification_notes", []),
                ),
            )
            return

        self.research_meta_var.set("No cached research yet for this listing.")
        self._set_text(
            self.research_summary_text,
            "\n".join(
                [
                    f"Target: {listing.contact_name or listing.contact_company or listing.title}",
                    f"Company: {listing.contact_company or '-'}",
                    f"Agent: {listing.contact_name or '-'}",
                    f"Project / Location: {' | '.join(part for part in [listing.project_name, listing.neighborhood, listing.location_text] if part) or '-'}",
                    "",
                    "Click 'Research Agent / Company' to run a live web lookup and cache the result for this listing.",
                ]
            ),
        )
        self._set_text(self.research_sources_text, "No cached web sources yet.")

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
            self.research_summary_text,
            self.research_sources_text,
        ):
            self._set_text(widget, "")
        self.subject_var.set("")
        self.recipient_email_var.set("")
        self.research_query_var.set("")
        self.research_meta_var.set("No cached research yet.")
        self.current_agent_research = None


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
        f"Viewed: {'Yes' if listing.viewed else 'No'}",
        f"Viewed At: {listing.viewed_at or '-'}",
        f"Emailed: {'Yes' if listing.emailed else 'No'}",
        f"Emailed At: {listing.emailed_at or '-'}",
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


def _research_sources_block(sources: list[dict], social_profiles: list[dict], verification_notes: list[str]) -> str:
    lines: list[str] = []
    if verification_notes:
        lines.append("Verification Notes:")
        lines.extend(f"- {note}" for note in verification_notes)
        lines.append("")

    if not sources:
        lines.append("No web sources stored.")
    else:
        lines.append("Web Sources:")
    for index, source in enumerate(sources, start=1):
        checks: list[str] = []
        if source.get("email_domain_match"):
            checks.append("email-domain match")
        if source.get("exact_email_match"):
            checks.append("exact email found")
        if source.get("phone_match"):
            checks.append("phone match")
        if source.get("is_portal"):
            checks.append("portal")
        if source.get("social_label"):
            checks.append(str(source.get("social_label")))
        lines.extend(
            [
                f"{index}. {source.get('title') or '-'}",
                f"   Domain: {source.get('domain') or '-'}",
                f"   URL: {source.get('url') or '-'}",
                f"   Checks: {', '.join(checks) if checks else '-'}",
                f"   Snippet: {source.get('snippet') or '-'}",
                f"   Page excerpt: {source.get('page_excerpt') or '-'}",
                "",
            ]
        )

    if social_profiles:
        lines.append("Social / Profile Hits:")
        for index, source in enumerate(social_profiles, start=1):
            lines.extend(
                [
                    f"{index}. {source.get('social_label') or source.get('domain') or '-'}",
                    f"   Title: {source.get('title') or '-'}",
                    f"   Domain: {source.get('domain') or '-'}",
                    f"   URL: {source.get('url') or '-'}",
                    "",
                ]
            )
    return "\n".join(lines).rstrip()
