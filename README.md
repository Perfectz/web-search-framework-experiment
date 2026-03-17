# Web Search Framework Experiment

Apartment Agent prototype for Bangkok apartment search automation.

Desktop apartment-search agent for Bangkok rentals, built to monitor Thai listing sites, score results against custom accessibility-focused criteria, and generate agent outreach emails that can be copied or opened directly in Gmail.

The current implementation is centered on `PropertyHub`, because its pages expose a structured Next.js payload that is much more reliable than brittle HTML scraping alone. Results are stored locally in SQLite, surfaced through a Tkinter desktop app, and enriched with agent contact details, match scoring, contact-tracking state, and draft emails.

## What This App Does

- Pulls apartment listings from configured Thai rental search pages
- Fetches richer detail pages for likely matches
- Extracts listing facts such as rent, size, beds/baths, project, transit references, amenities, and agent contact details
- Scores listings against user-defined criteria such as budget, size, bedroom count, target neighborhoods, and walkability cues
- Deduplicates repeated listings in SQLite
- Generates first-contact outreach emails for real-estate agents
- Opens Gmail with the draft prefilled, or copies the draft to the clipboard
- Lets you mark listings as `contacted` or `not contacted`
- Shows listing date and contact state directly in the desktop UI
- Writes JSON and Markdown reports for each collection run
- Optionally captures screenshots with Playwright for manual review

## Why I Built It This Way

The goal was not just to scrape listing pages. The real workflow was:

1. Search repeatedly for apartments in a very specific Bangkok corridor
2. Keep only listings that fit a real-life living situation
3. Track which agents have already been contacted
4. Open a ready-to-send outreach message quickly

Because of that, the app was built as a local workflow tool instead of a pure crawler.

Key design decisions:

- `Python` for fast iteration and a low-friction local toolchain
- `Tkinter` for the desktop app because it ships with Python and can be built quickly without a frontend stack
- `SQLite` for persistent local tracking of listings, drafts, and contacted status
- Adapter-based site collection so each portal can have its own extraction logic
- Structured payload extraction from `__NEXT_DATA__` on PropertyHub instead of relying only on CSS selectors
- Deterministic email generation so the outreach flow works without requiring an LLM or API key
- Optional Playwright support as a fallback for browser screenshots and future browser-control workflows

## How It Was Built

This project was assembled in layers:

### 1. Core data model

The first step was defining stable Python dataclasses for:

- search criteria
- search sources
- listings
- email drafts

That created one consistent schema for scraped data, scoring, UI display, email drafting, and persistence.

### 2. Matching and ranking

The next step was implementing a rules-based matcher that scores listings for:

- budget fit
- bedroom count
- minimum size
- target neighborhoods and transit anchors
- walkability / park-related cues
- furnishing preference
- conflicting or suspicious data

This keeps the decision process inspectable and easy to tune.

### 3. Persistence

SQLite was added to:

- keep listing history across runs
- deduplicate repeated or reposted units
- store generated drafts
- preserve `contacted` state even after a fresh search

### 4. Site adapter

PropertyHub was implemented first because it exposes rich embedded JSON data. That made it possible to extract:

- listing IDs
- prices
- room details
- project names
- contact information
- dates
- amenities and facilities

without depending entirely on fragile visual scraping.

### 5. Reporting and CLI

A command-line runner was added to support:

- seed/demo runs
- live runs
- daily scheduled runs
- screenshot capture
- launching the desktop app

Each run also produces a JSON and Markdown report under `outputs/`.

### 6. Desktop workflow app

Finally, a local Tkinter app was added so the project is actually usable day-to-day.

The app lets you:

- run the search
- filter and search results
- review agent contact info
- see listing dates
- mark listings as contacted
- regenerate outreach drafts
- copy drafts
- open a prefilled Gmail compose window

## Current Scope

Implemented:

- `PropertyHub` zone pages
- `PropertyHub` project pages
- `PropertyHub` listing detail pages
- SQLite persistence
- results viewer desktop app
- Gmail draft opening
- contacted tracking
- listing date display
- optional Playwright screenshot capture

Not implemented yet:

- DDproperty adapter
- Thailand-Property adapter
- RentHub adapter
- PropertyScout adapter
- OCR / vision extraction from screenshots
- automatic email sending
- multi-user or hosted deployment

## Project Structure

- `apartment_agent/models.py`
  Core dataclasses for criteria, sources, listings, and drafts
- `apartment_agent/adapters/propertyhub.py`
  PropertyHub collection logic
- `apartment_agent/matching.py`
  Rules-based scoring and conflict detection
- `apartment_agent/storage.py`
  SQLite persistence, draft storage, contacted tracking, and list/query helpers
- `apartment_agent/email_drafts.py`
  Outreach email generation
- `apartment_agent/gui.py`
  Tkinter desktop app
- `apartment_agent/cli.py`
  CLI entrypoints for runs, app launch, and screenshot capture
- `config/criteria.json`
  User criteria and outreach context
- `config/sources.json`
  Source pages to monitor
- `config/seed_listings.json`
  Seed/test data

## Quick Start

### 1. Run a seeded demo

```powershell
python -m apartment_agent run-seed --criteria config/criteria.json --seed config/seed_listings.json
```

### 2. Run a live collection

```powershell
python -m apartment_agent run --criteria config/criteria.json --sources config/sources.json
```

### 3. Open the desktop app

```powershell
python -m apartment_agent app
```

### 4. Optional: capture a page screenshot with Playwright

```powershell
pip install -r requirements-optional.txt
playwright install chromium
python -m apartment_agent capture --url "https://propertyhub.in.th/en/condo-for-rent/mrt-chatuchak-park" --output screenshots/chatuchak-park.png
```

## Desktop App Workflow

Inside the app you can:

- click `Run Search` to refresh listings
- use `Filter` to switch between `alert`, `watch`, and `reject`
- use `Contacted` to show only contacted or uncontacted listings
- search by title, project, URL, site, or listing ID
- select a result to inspect contact info, match reasons, flags, and summary
- click `Mark Contacted` once you have reached out
- click `Regenerate Draft` to rebuild the latest email from the current template
- click `Open Gmail Draft` to open a browser tab with the draft prefilled
- click `Copy Email` to paste the message elsewhere

## Daily Runs

The simplest Windows setup is Task Scheduler calling:

```powershell
python -m apartment_agent run --criteria config/criteria.json --sources config/sources.json
```

There is also a built-in long-running scheduler:

```powershell
python -m apartment_agent run-daily --criteria config/criteria.json --sources config/sources.json --time 09:00 --timezone Asia/Bangkok
```

## How Matching Works

Listings are scored based on:

- maximum monthly rent
- minimum bedrooms
- minimum size
- preferred locations and transit anchors
- park and walkability cues
- furnishing preference
- page/data conflicts
- missing or unreliable detail pages

Listings are then labeled:

- `alert` for strong candidates
- `watch` for possible candidates
- `reject` for poor fits

## Outreach Emails

Draft emails are generated from:

- the selected listing details
- stored outreach context in `config/criteria.json`
- accessibility/mobility requirements
- the requested Bangkok viewing window
- one or two listing-specific questions

If an agent email is available, the Gmail action prefills the recipient as well.

## Contact Tracking

Each listing now stores:

- `contacted`
- `contacted_at`
- `listing_date`

This makes it possible to filter for listings you still need to contact and avoid losing state after re-running the search.

## Notes and Limitations

- The project currently relies most heavily on PropertyHub.
- Older stored listings may not have a listing date until a fresh search refreshes them.
- Some sites redirect or expose inconsistent fields, so future adapters will still need site-specific handling.
- This is a local desktop tool, not a hosted SaaS product.
- Email sending is not automatic; the current flow is review-first and manual-send by design.

## Testing

```powershell
python -m unittest discover -s tests -v
python -m compileall apartment_agent tests
```

## Repo Summary

This repo is a pragmatic local apartment-hunting workflow tool. It combines site collection, ranking, persistence, contact management, and email drafting into one desktop application so apartment outreach is fast and organized instead of spread across browser tabs, chat logs, and copied notes.
