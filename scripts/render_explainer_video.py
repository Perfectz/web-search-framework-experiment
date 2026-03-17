from __future__ import annotations

import math
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageGrab

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apartment_agent.gui import ApartmentAgentApp, build_gmail_compose_url

DOCS_DIR = ROOT / "docs"
SOURCE_DB = ROOT / "data" / "apartment_agent.sqlite"
CRITERIA_PATH = ROOT / "config" / "criteria.json"
SOURCES_PATH = ROOT / "config" / "sources.json"
OUTPUTS_PATH = ROOT / "outputs"
VIDEO_PATH = DOCS_DIR / "app-explainer.mp4"
POSTER_PATH = DOCS_DIR / "app-explainer-poster.png"

FPS = 30
VIDEO_SIZE = (1600, 900)
TIMELINE = ["DISCOVER", "TRIAGE", "VERIFY", "CUT", "DRAFT", "SEND"]


def main() -> None:
    if not SOURCE_DB.exists():
        raise SystemExit(f"Missing database: {SOURCE_DB}")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    assets = _capture_assets()
    with tempfile.TemporaryDirectory() as temp_dir:
        frames_dir = Path(temp_dir) / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        _render_video_frames(frames_dir, assets)
        _encode_video(frames_dir, VIDEO_PATH)
    _build_poster(assets).save(POSTER_PATH, format="PNG")
    print(VIDEO_PATH)
    print(POSTER_PATH)


def _capture_assets() -> dict[str, object]:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_db = Path(temp_dir) / "demo.sqlite"
        shutil.copy2(SOURCE_DB, temp_db)
        app = ApartmentAgentApp(
            db_path=str(temp_db),
            criteria_path=str(CRITERIA_PATH),
            sources_path=str(SOURCES_PATH),
            output_dir=str(OUTPUTS_PATH),
        )
        try:
            app.attributes("-topmost", True)
            app.geometry("1600x900+30+30")
            app.update()
            time.sleep(0.4)

            _select_first(app)
            app.notebook.select(app.details_tab)
            app.update()

            assets: dict[str, object] = {
                "overview": _capture_window(app),
                "overview_boxes": {
                    "run": _widget_box(app, app.run_button),
                    "results": _widget_box(app, app.tree),
                    "contact": _widget_box(app, app.contact_text.master),
                    "open_listing": _widget_box(app, app.open_listing_button),
                    "hide": _widget_box(app, app.hide_listing_button),
                },
            }

            app.filter_var.set("alert")
            app.sort_var.set("newest")
            app.refresh_results()
            _select_first(app)
            app.notebook.select(app.details_tab)
            app.update()
            assets["triage"] = _capture_window(app)
            assets["triage_boxes"] = {
                "filter": _widget_box(app, app.filter_box),
                "sort": _widget_box(app, app.sort_box),
                "results": _widget_box(app, app.tree),
                "contact": _widget_box(app, app.contact_text.master),
            }

            assets["listing_click"] = assets["triage"]
            assets["listing_button_box"] = _widget_box(app, app.open_listing_button)
            listing = app.selected_listing
            assets["listing_url"] = listing.url if listing and listing.url else "https://example.com/listing"
            assets["listing_title"] = listing.title if listing else "Original listing"
            assets["listing_page"] = _capture_listing_page(str(assets["listing_url"]), str(assets["listing_title"]))

            if app.selected_listing:
                app.set_not_interested(True)
            app.interest_filter_var.set("not_interested")
            app.refresh_results()
            _select_first(app)
            app.notebook.select(app.details_tab)
            app.update()
            assets["hidden"] = _capture_window(app)
            assets["hidden_boxes"] = {
                "interest": _widget_box(app, app.interest_box),
                "restore": _widget_box(app, app.restore_listing_button),
                "results": _widget_box(app, app.tree),
            }

            app.interest_filter_var.set("active")
            app.filter_var.set("alert")
            app.sort_var.set("best_match")
            app.search_var.set("")
            app.refresh_results()
            _select_first(app)
            app.notebook.select(app.email_tab)
            app.regenerate_draft()
            app.update()
            time.sleep(0.2)
            assets["email"] = _capture_window(app)
            assets["email_boxes"] = {
                "subject": _widget_box(app, app.subject_entry),
                "body": _widget_box(app, app.email_body_text.master),
                "gmail": _widget_box(app, app.open_gmail_button),
            }
            assets["gmail_click"] = assets["email"]
            assets["gmail_button_box"] = _widget_box(app, app.open_gmail_button)

            listing = app.selected_listing
            to = listing.contact_email if listing and listing.contact_email else "agent@example.com"
            subject = app.subject_var.get().strip()
            body = app.email_body_text.get("1.0", "end").strip()
            assets["gmail_url"] = build_gmail_compose_url(to=to, subject=subject, body=body)
            assets["gmail_browser"] = _gmail_mock(to=to, subject=subject, body=body)
            return assets
        finally:
            app.destroy()


def _capture_listing_page(url: str, title: str) -> Image.Image:
    try:
        from apartment_agent.browser import PlaywrightCapture

        capture = PlaywrightCapture(headless=True, wait_seconds=2.5)
        snapshot = capture.snapshot(url, include_links=False)
        challenge_text = f"{snapshot.get('title', '')}\n{snapshot.get('text', '')}".lower()
        if any(token in challenge_text for token in ["just a moment", "security verification", "cloudflare"]):
            return _listing_fallback_mock(url, title)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "listing.png"
            capture.capture(url, path)
            return Image.open(path).convert("RGB")
    except Exception:
        return _listing_fallback_mock(url, title)


def _render_video_frames(frames_dir: Path, assets: dict[str, object]) -> None:
    scenes = [
        (2.2, lambda t: _render_intro(t)),
        (3.3, lambda t: _render_feature_scene(
            image=assets["overview"],
            boxes=assets["overview_boxes"],
            title="This app runs the apartment workflow end to end",
            body="It searches saved sources, ranks listings, shows contact context, opens the original listing, and lets you kill bad leads without losing track.",
            kicker="WHAT IT DOES",
            accent="#44E4FF",
            step=0,
            t=t,
            callouts=[
                {"key": "run", "label": "Run the saved search pipeline", "offset": (-220, -118), "delay": 0.05, "accent": "#44E4FF", "index": 1},
                {"key": "results", "label": "Ranked listings from SQLite", "offset": (-265, 90), "delay": 0.24, "accent": "#37F0C2", "index": 2},
                {"key": "contact", "label": "Agent details and fit context", "offset": (120, -60), "delay": 0.44, "accent": "#FFB14A", "index": 3},
                {"key": "open_listing", "label": "Open the real source page", "offset": (106, -120), "delay": 0.64, "accent": "#44B3FF", "index": 4},
                {"key": "hide", "label": "Hide dead-end listings", "offset": (112, 42), "delay": 0.82, "accent": "#FF6F7A", "index": 5},
            ],
        )),
        (2.6, lambda t: _render_feature_scene(
            image=assets["triage"],
            boxes=assets["triage_boxes"],
            title="Filter by fit and sort by date when speed matters",
            body="Date sorting and scoring are both visible in the same workspace, so you can push fresh inventory and strong matches to the front.",
            kicker="TRIAGE FAST",
            accent="#37F0C2",
            step=1,
            t=t,
            callouts=[
                {"key": "filter", "label": "Fit filter", "offset": (-120, -108), "delay": 0.08, "accent": "#37F0C2", "index": 1},
                {"key": "sort", "label": "Newest-first sort", "offset": (12, -108), "delay": 0.28, "accent": "#FFB14A", "index": 2},
                {"key": "results", "label": "Scored listings in review order", "offset": (-250, 90), "delay": 0.48, "accent": "#44E4FF", "index": 3},
                {"key": "contact", "label": "Review the agent context here", "offset": (120, -12), "delay": 0.68, "accent": "#8A7DFF", "index": 4},
            ],
        )),
        (1.6, lambda t: _render_click_scene(
            image=assets["listing_click"],
            button_box=assets["listing_button_box"],
            title="Click through to the original listing",
            body="One click from the ranked view to the real property page.",
            kicker="VERIFY SOURCE",
            accent="#44B3FF",
            step=2,
            t=t,
        )),
        (2.0, lambda t: _render_browser_scene(
            content=assets["listing_page"],
            url=str(assets["listing_url"]),
            page_title=str(assets["listing_title"]),
            title="Review the live page before contacting the agent",
            body="The point is control. The app gets you to the source listing fast instead of hiding the underlying portal.",
            kicker="ORIGINAL PAGE",
            accent="#44B3FF",
            step=2,
            t=t,
        )),
        (2.2, lambda t: _render_feature_scene(
            image=assets["hidden"],
            boxes=assets["hidden_boxes"],
            title="Hide weak leads and keep the queue clean",
            body="Mark a listing as not interested once, then keep it out of the active review flow until you choose to restore it.",
            kicker="CUT BAD FITS",
            accent="#FF6F7A",
            step=3,
            t=t,
            callouts=[
                {"key": "interest", "label": "Interest filter shows hidden items", "offset": (-90, -106), "delay": 0.08, "accent": "#FF6F7A", "index": 1},
                {"key": "restore", "label": "Restore the listing here", "offset": (110, 24), "delay": 0.38, "accent": "#44E4FF", "index": 2},
                {"key": "results", "label": "Bad leads stay out of your active queue", "offset": (-250, 95), "delay": 0.64, "accent": "#FFB14A", "index": 3},
            ],
        )),
        (2.3, lambda t: _render_feature_scene(
            image=assets["email"],
            boxes=assets["email_boxes"],
            title="The outreach draft already lives inside the app",
            body="Subject, email body, and the Gmail handoff button sit in the same screen as the listing context.",
            kicker="DRAFT INSIDE",
            accent="#8A7DFF",
            step=4,
            t=t,
            callouts=[
                {"key": "subject", "label": "Editable subject line", "offset": (-240, -88), "delay": 0.08, "accent": "#8A7DFF", "index": 1},
                {"key": "body", "label": "Draft body generated here", "offset": (108, -28), "delay": 0.34, "accent": "#44E4FF", "index": 2},
                {"key": "gmail", "label": "Open Gmail prefilled", "offset": (86, -110), "delay": 0.6, "accent": "#37F0C2", "index": 3},
            ],
        )),
        (1.6, lambda t: _render_click_scene(
            image=assets["gmail_click"],
            button_box=assets["gmail_button_box"],
            title="Open Gmail with the draft already loaded",
            body="Recipient, subject, and body are already there. The app gets you straight to send-ready.",
            kicker="OPEN EMAIL",
            accent="#8A7DFF",
            step=5,
            t=t,
        )),
        (2.3, lambda t: _render_browser_scene(
            content=assets["gmail_browser"],
            url=str(assets["gmail_url"]),
            page_title="Gmail Draft",
            title="Your email opens prefilled for the agent",
            body="That handoff is the payoff: less friction, less tab churn, and faster outreach.",
            kicker="SEND READY",
            accent="#8A7DFF",
            step=5,
            t=t,
        )),
        (2.0, lambda t: _render_outro(t)),
    ]

    frame_index = 0
    for duration, renderer in scenes:
        total_frames = max(1, int(round(duration * FPS)))
        for scene_frame in range(total_frames):
            t = scene_frame / max(1, total_frames - 1)
            renderer(t).save(frames_dir / f"frame_{frame_index:05d}.png", format="PNG")
            frame_index += 1


def _render_intro(t: float) -> Image.Image:
    frame = _background()
    draw = ImageDraw.Draw(frame)
    _panel(frame, (84, 84, 820, 556), "#44E4FF")
    _pill(draw, (118, 118, 538, 162), "WEB SEARCH FRAMEWORK EXPERIMENT", _font_mono(21, True), "#08131F", "#44E4FF")
    _text(draw, "Apartment Agent", (118, 214), _font_ui(82, True), "#F7FBFF")
    _text(draw, "Search. Rank. Verify. Draft. Send.", (122, 314), _font_ui(42, True), "#44E4FF")
    _paragraph(
        draw,
        "A sci-fi explainer built from live app screenshots.\nVibe coded in about an hour, then tightened to actually explain the workflow.",
        (124, 410, 760, 520),
        _font_ui(30),
        "#C8D7E5",
        12,
    )
    badge = _badge("REAL UI // REAL CLICK PATHS // REAL EMAIL HANDOFF", "#8A7DFF")
    badge = badge.resize((int(badge.width * (0.94 + 0.06 * math.sin(t * math.pi))), int(badge.height * (0.94 + 0.06 * math.sin(t * math.pi)))))
    frame.alpha_composite(badge, (118, 610))
    _timeline(frame, -1)
    return frame.convert("RGB")


def _render_feature_scene(*, image, boxes, title: str, body: str, kicker: str, accent: str, step: int, t: float, callouts: list[dict[str, object]]) -> Image.Image:
    frame = _background()
    draw = ImageDraw.Draw(frame)
    _header(draw, kicker, title, body, accent)
    layout = _screen(frame, image, (470, 180, 1510, 820), "contain", 1.0)
    _callouts(frame, image.size, layout, boxes, callouts, t)
    _timeline(frame, step)
    return frame.convert("RGB")


def _render_click_scene(*, image, button_box, title: str, body: str, kicker: str, accent: str, step: int, t: float) -> Image.Image:
    frame = _background()
    draw = ImageDraw.Draw(frame)
    _header(draw, kicker, title, body, accent)
    layout = _screen(frame, image, (520, 180, 1510, 820), "contain", 1.0)
    mapped_box = _map_box(button_box, image.size, layout)
    _focus_box(frame, mapped_box, accent, 0.5 + 0.5 * math.sin(min(1.0, t / 0.72) * math.pi))
    center = _center(mapped_box)
    start = (center[0] - 250, center[1] + 150)
    _cursor(frame, _lerp(start, center, min(1.0, t / 0.72)))
    if t > 0.72:
        _ripple(frame, center, accent, (t - 0.72) / 0.28)
    frame.alpha_composite(_badge("ACTUAL APP BUTTON CLICK", accent), (110, 692))
    _timeline(frame, step)
    return frame.convert("RGB")


def _render_browser_scene(*, content, url: str, page_title: str, title: str, body: str, kicker: str, accent: str, step: int, t: float) -> Image.Image:
    frame = _background()
    draw = ImageDraw.Draw(frame)
    _header(draw, kicker, title, body, accent)
    browser = _browser(content, url, page_title)
    _screen(frame, browser, (540, 170, 1515, 825), "cover", 0.96 + 0.05 * _ease(t))
    frame.alpha_composite(_badge("BROWSER HANDOFF SHOWN IN THE VIDEO", accent), (110, 692))
    _timeline(frame, step)
    return frame.convert("RGB")


def _render_outro(t: float) -> Image.Image:
    frame = _background()
    draw = ImageDraw.Draw(frame)
    _panel(frame, (92, 94, 1120, 610), "#8A7DFF")
    _pill(draw, (126, 126, 398, 170), "VIBE CODED FAST", _font_mono(22, True), "#130B22", "#8A7DFF")
    _text(draw, "Cool enough to show off,", (126, 224), _font_ui(74, True), "#F7FBFF")
    _text(draw, "clear enough to understand.", (126, 310), _font_ui(74, True), "#44E4FF")
    _paragraph(
        draw,
        "The app searches sources, sorts by date, opens the original listing,\nhides bad fits, and launches a Gmail draft for the agent.\nBuilt in about an hour. Sharp enough to use for real.",
        (130, 424, 1060, 560),
        _font_ui(30),
        "#C8D7E5",
        12,
    )
    badge = _badge("docs/app-explainer.mp4", "#37F0C2")
    badge = badge.resize((int(badge.width * (0.94 + 0.06 * math.sin(t * math.pi))), int(badge.height * (0.94 + 0.06 * math.sin(t * math.pi)))))
    frame.alpha_composite(badge, (126, 688))
    _timeline(frame, 5)
    return frame.convert("RGB")


def _build_poster(assets: dict[str, object]) -> Image.Image:
    return _render_feature_scene(
        image=assets["overview"],
        boxes=assets["overview_boxes"],
        title="This app runs the apartment workflow end to end",
        body="It searches saved sources, ranks listings, shows contact context, opens the original listing, and lets you kill bad leads without losing track.",
        kicker="WHAT IT DOES",
        accent="#44E4FF",
        step=0,
        t=0.96,
        callouts=[
            {"key": "run", "label": "Run the saved search pipeline", "offset": (-220, -118), "delay": 0.05, "accent": "#44E4FF", "index": 1},
            {"key": "results", "label": "Ranked listings from SQLite", "offset": (-265, 90), "delay": 0.24, "accent": "#37F0C2", "index": 2},
            {"key": "contact", "label": "Agent details and fit context", "offset": (120, -60), "delay": 0.44, "accent": "#FFB14A", "index": 3},
            {"key": "open_listing", "label": "Open the real source page", "offset": (106, -120), "delay": 0.64, "accent": "#44B3FF", "index": 4},
            {"key": "hide", "label": "Hide dead-end listings", "offset": (112, 42), "delay": 0.82, "accent": "#FF6F7A", "index": 5},
        ],
    )


def _header(draw: ImageDraw.ImageDraw, kicker: str, title: str, body: str, accent: str) -> None:
    _pill(draw, (90, 80, 306, 120), kicker, _font_mono(18, True), "#07121F", accent)
    _text(draw, title, (90, 144), _font_ui(52, True), "#F6FBFF")
    _paragraph(draw, body, (94, 230, 452, 382), _font_ui(24), "#C8D6E4", 10)


def _screen(frame: Image.Image, image: Image.Image, box: tuple[int, int, int, int], mode: str, scale: float) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    width = right - left
    height = bottom - top
    scaled_width = int(width * scale)
    scaled_height = int(height * scale)
    scaled_left = left + (width - scaled_width) // 2
    scaled_top = top + (height - scaled_height) // 2
    scaled_right = scaled_left + scaled_width
    scaled_bottom = scaled_top + scaled_height

    bezel = 20
    panel = Image.new("RGBA", (scaled_width, scaled_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(panel)
    draw.rounded_rectangle((0, 0, scaled_width - 1, scaled_height - 1), radius=28, fill=(8, 14, 30, 228), outline=(95, 150, 255, 120), width=2)
    draw.rounded_rectangle((10, 10, scaled_width - 11, scaled_height - 11), radius=24, outline=(255, 255, 255, 24), width=1)

    inner = (bezel, bezel, scaled_width - bezel, scaled_height - bezel)
    inner_width = inner[2] - inner[0]
    inner_height = inner[3] - inner[1]
    content = image.convert("RGBA")
    if mode == "cover":
        content = _cover_resize(content, (inner_width, inner_height))
    else:
        content = _fit(content, (inner_width, inner_height))
    content_left = inner[0] + (inner_width - content.width) // 2
    content_top = inner[1] + (inner_height - content.height) // 2
    panel.alpha_composite(content, (content_left, content_top))

    overlay = Image.new("RGBA", panel.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    for y in range(18, panel.height, 6):
        overlay_draw.line((14, y, panel.width - 14, y), fill=(255, 255, 255, 6), width=1)
    panel = Image.alpha_composite(panel, overlay)

    frame.alpha_composite(panel, (scaled_left, scaled_top))
    _draw_corners(frame, (scaled_left, scaled_top, scaled_right, scaled_bottom), "#44E4FF")
    return (
        scaled_left + content_left,
        scaled_top + content_top,
        scaled_left + content_left + content.width,
        scaled_top + content_top + content.height,
    )


def _callouts(
    frame: Image.Image,
    source_size: tuple[int, int],
    layout: tuple[int, int, int, int],
    boxes: dict[str, tuple[int, int, int, int]],
    callouts: list[dict[str, object]],
    t: float,
) -> None:
    for item in callouts:
        delay = float(item.get("delay", 0.0))
        progress = _ease((t - delay) / max(0.0001, 1.0 - delay))
        if progress <= 0:
            continue
        key = str(item["key"])
        if key not in boxes:
            continue
        accent = str(item.get("accent", "#44E4FF"))
        mapped = _map_box(boxes[key], source_size, layout)
        _focus_box(frame, mapped, accent, progress)

        anchor = _center(mapped)
        offset_x, offset_y = item.get("offset", (0, 0))
        label_center = (anchor[0] + int(offset_x), anchor[1] + int(offset_y))
        label_text = f"{int(item.get('index', 1))}. {str(item['label'])}"
        label_image = _badge(label_text, accent)
        label_image = label_image.resize(
            (
                max(1, int(label_image.width * (0.75 + 0.25 * progress))),
                max(1, int(label_image.height * (0.75 + 0.25 * progress))),
            ),
            Image.Resampling.LANCZOS,
        )
        label_box = (
            int(label_center[0] - label_image.width / 2),
            int(label_center[1] - label_image.height / 2),
            int(label_center[0] + label_image.width / 2),
            int(label_center[1] + label_image.height / 2),
        )
        frame.alpha_composite(label_image, (label_box[0], label_box[1]))

        start = _closest_point_on_rect(mapped, label_center)
        end = _closest_point_on_rect(label_box, anchor)
        draw = ImageDraw.Draw(frame)
        draw.line((start[0], start[1], end[0], end[1]), fill=ImageColor.getrgb(accent) + (int(180 * progress),), width=3)
        draw.ellipse((start[0] - 4, start[1] - 4, start[0] + 4, start[1] + 4), fill=ImageColor.getrgb(accent) + (220,))


def _focus_box(frame: Image.Image, box: tuple[int, int, int, int], accent: str, strength: float) -> None:
    alpha = int(200 * max(0.0, min(1.0, strength)))
    glow = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    rgb = ImageColor.getrgb(accent)
    for spread, opacity in ((16, alpha // 5), (10, alpha // 3), (4, alpha)):
        draw.rounded_rectangle(
            (box[0] - spread, box[1] - spread, box[2] + spread, box[3] + spread),
            radius=14,
            outline=rgb + (opacity,),
            width=3,
        )
    frame.alpha_composite(glow)


def _cursor(frame: Image.Image, position: tuple[float, float]) -> None:
    x, y = int(position[0]), int(position[1])
    cursor = Image.new("RGBA", (56, 72), (0, 0, 0, 0))
    draw = ImageDraw.Draw(cursor)
    draw.polygon([(8, 6), (8, 58), (21, 45), (31, 67), (42, 62), (30, 40), (48, 40)], fill=(247, 251, 255, 255), outline=(12, 22, 34, 255))
    draw.line((19, 44, 34, 59), fill=(12, 22, 34, 255), width=2)
    frame.alpha_composite(cursor, (x - 10, y - 8))


def _ripple(frame: Image.Image, center: tuple[int, int], accent: str, progress: float) -> None:
    progress = max(0.0, min(1.0, progress))
    ripple = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(ripple)
    rgb = ImageColor.getrgb(accent)
    max_radius = 84
    radius = int(24 + max_radius * progress)
    alpha = int(180 * (1.0 - progress))
    draw.ellipse((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), outline=rgb + (alpha,), width=4)
    draw.ellipse((center[0] - 12, center[1] - 12, center[0] + 12, center[1] + 12), fill=rgb + (140,))
    frame.alpha_composite(ripple)


def _browser(content: Image.Image, url: str, page_title: str) -> Image.Image:
    width = 1080
    height = 720
    browser = Image.new("RGBA", (width, height), (5, 11, 24, 255))
    draw = ImageDraw.Draw(browser)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=26, fill=(8, 14, 28, 255), outline=(255, 255, 255, 34), width=1)
    draw.rounded_rectangle((18, 18, width - 18, 86), radius=18, fill=(14, 22, 38, 255))
    for index, color in enumerate(("#FF6F7A", "#FFB14A", "#37F0C2")):
        x = 42 + index * 22
        draw.ellipse((x, 42, x + 12, 54), fill=ImageColor.getrgb(color))
    draw.rounded_rectangle((150, 34, width - 36, 68), radius=15, fill=(7, 12, 24, 255), outline=(68, 114, 189, 110), width=1)
    draw.text((170, 40), _truncate(url, 92), fill="#D4E6F9", font=_font_mono(17))
    draw.text((34, 102), _truncate(page_title, 56), fill="#F6FBFF", font=_font_ui(24, True))

    content_box = (28, 144, width - 28, height - 28)
    content_rgba = content.convert("RGBA")
    content_rgba = _cover_resize(content_rgba, (content_box[2] - content_box[0], content_box[3] - content_box[1]))
    browser.alpha_composite(content_rgba, (content_box[0], content_box[1]))

    overlay = Image.new("RGBA", browser.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rounded_rectangle((content_box[0], content_box[1], content_box[2], content_box[3]), radius=18, outline=(255, 255, 255, 28), width=1)
    browser = Image.alpha_composite(browser, overlay)
    return browser


def _gmail_mock(to: str, subject: str, body: str) -> Image.Image:
    width = 1120
    height = 720
    frame = Image.new("RGBA", (width, height), (247, 248, 250, 255))
    draw = ImageDraw.Draw(frame)
    draw.rectangle((0, 0, width, 84), fill=(232, 234, 237, 255))
    draw.text((34, 24), "Gmail", fill="#CC4337", font=_font_ui(30, True))
    draw.rounded_rectangle((72, 130, width - 72, height - 72), radius=24, fill=(255, 255, 255, 255), outline=(214, 220, 226, 255), width=2)
    draw.text((106, 164), "New Message", fill="#202124", font=_font_ui(26, True))
    _gmail_row(draw, "To", to or "agent@example.com", 104, 220, width - 104)
    _gmail_row(draw, "Subject", subject, 104, 280, width - 104)
    draw.text((106, 344), "Message", fill="#5F6368", font=_font_ui(18))
    _paragraph(draw, body, (106, 380, width - 112, height - 146), _font_ui(20), "#202124", 8)
    draw.rounded_rectangle((106, height - 128, 254, height - 82), radius=20, fill=(26, 115, 232, 255))
    draw.text((154, height - 118), "Send", fill="#FFFFFF", font=_font_ui(22, True))
    return frame


def _gmail_row(draw: ImageDraw.ImageDraw, label: str, value: str, left: int, top: int, right: int) -> None:
    draw.text((left, top), label, fill="#5F6368", font=_font_ui(18))
    draw.line((left, top + 32, right, top + 32), fill="#DADCE0", width=1)
    draw.text((left + 86, top - 2), _truncate(value or "-", 78), fill="#202124", font=_font_ui(20))


def _listing_fallback_mock(url: str, title: str) -> Image.Image:
    width = 1120
    height = 720
    image = Image.new("RGBA", (width, height), (248, 250, 253, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 78), fill=(15, 23, 42, 255))
    draw.text((28, 24), "Listing Preview", fill="#F8FAFC", font=_font_ui(28, True))
    draw.rounded_rectangle((56, 120, width - 56, height - 56), radius=28, fill=(255, 255, 255, 255), outline=(210, 220, 232, 255), width=2)
    draw.rounded_rectangle((86, 158, width - 86, 412), radius=22, fill=(223, 232, 243, 255))
    draw.text((94, 440), _truncate(title, 72), fill="#0F172A", font=_font_ui(30, True))
    _paragraph(
        draw,
        "Fallback browser preview used when the source portal blocks screenshots or throws a challenge page. The explainer still shows the handoff clearly.",
        (94, 492, width - 92, 602),
        _font_ui(22),
        "#334155",
        8,
    )
    draw.text((94, 634), _truncate(url, 88), fill="#2563EB", font=_font_mono(17))
    return image


def _panel(frame: Image.Image, box: tuple[int, int, int, int], accent: str) -> None:
    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    rgb = ImageColor.getrgb(accent)
    for spread, opacity in ((40, 24), (22, 38), (10, 56)):
        draw.rounded_rectangle(
            (box[0] - spread, box[1] - spread, box[2] + spread, box[3] + spread),
            radius=34,
            outline=rgb + (opacity,),
            width=3,
        )
    draw.rounded_rectangle(box, radius=28, fill=(7, 12, 24, 194), outline=rgb + (140,), width=2)
    frame.alpha_composite(overlay)


def _pill(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, font: ImageFont.ImageFont, bg: str, fg: str) -> None:
    draw.rounded_rectangle(box, radius=(box[3] - box[1]) // 2, fill=bg, outline=ImageColor.getrgb(fg) + (180,), width=2)
    text_box = draw.textbbox((0, 0), text, font=font)
    text_width = text_box[2] - text_box[0]
    text_height = text_box[3] - text_box[1]
    x = box[0] + (box[2] - box[0] - text_width) // 2
    y = box[1] + (box[3] - box[1] - text_height) // 2 - 1
    draw.text((x, y), text, fill=fg, font=font)


def _text(draw: ImageDraw.ImageDraw, text: str, position: tuple[int, int], font: ImageFont.ImageFont, fill: str) -> None:
    draw.text(position, text, font=font, fill=fill)


def _paragraph(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
    font: ImageFont.ImageFont,
    fill: str,
    spacing: int,
) -> None:
    lines: list[str] = []
    max_width = box[2] - box[0]
    for paragraph in text.splitlines():
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            width = draw.textbbox((0, 0), candidate, font=font)[2]
            if width <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    draw.multiline_text((box[0], box[1]), "\n".join(lines), font=font, fill=fill, spacing=spacing)


def _badge(text: str, accent: str) -> Image.Image:
    pad_x = 20
    pad_y = 12
    font = _font_mono(18, True)
    temp = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(temp)
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0] + pad_x * 2
    height = bbox[3] - bbox[1] + pad_y * 2
    badge = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(badge)
    rgb = ImageColor.getrgb(accent)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=height // 2, fill=(7, 12, 24, 224), outline=rgb + (180,), width=2)
    draw.text((pad_x, pad_y - 1), text, fill=accent, font=font)
    return badge


def _font_ui(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/segoeuib.ttf") if bold else Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf") if bold else Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _font_mono(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/consolab.ttf") if bold else Path("C:/Windows/Fonts/consola.ttf"),
        Path("C:/Windows/Fonts/courbd.ttf") if bold else Path("C:/Windows/Fonts/cour.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _timeline(frame: Image.Image, step: int) -> None:
    draw = ImageDraw.Draw(frame)
    left = 604
    top = 852
    gap = 132
    for index, label in enumerate(TIMELINE):
        active = index <= step
        x = left + index * gap
        color = "#44E4FF" if active else "#5B6B82"
        if index < len(TIMELINE) - 1:
            draw.line((x + 92, top + 16, x + gap - 16, top + 16), fill=ImageColor.getrgb(color) + (160 if active else 70,), width=3)
        badge = _badge(label, color if active else "#5B6B82")
        frame.alpha_composite(badge, (x, top - 10))


def _background() -> Image.Image:
    width, height = VIDEO_SIZE
    x = np.linspace(-1.0, 1.0, width)[None, :]
    y = np.linspace(0.0, 1.0, height)[:, None]
    top = np.array([5.0, 10.0, 22.0])
    bottom = np.array([3.0, 7.0, 16.0])
    base = ((1.0 - y)[..., None] * top + y[..., None] * bottom).astype(np.float32)
    base = np.repeat(base, width, axis=1)
    glow_left = np.exp(-(((x + 0.55) ** 2) / 0.08 + ((y - 0.18) ** 2) / 0.05))[..., None] * np.array([0.0, 110.0, 170.0])
    glow_right = np.exp(-(((x - 0.58) ** 2) / 0.09 + ((y - 0.72) ** 2) / 0.08))[..., None] * np.array([88.0, 30.0, 150.0])
    arr = np.clip(base + glow_left + glow_right, 0, 255).astype(np.uint8)
    alpha = np.full((height, width, 1), 255, dtype=np.uint8)
    frame = Image.fromarray(np.concatenate([arr, alpha], axis=2))
    draw = ImageDraw.Draw(frame)
    for y_pos in range(0, height, 48):
        draw.line((0, y_pos, width, y_pos), fill=(255, 255, 255, 8), width=1)
    for x_pos in range(0, width, 64):
        draw.line((x_pos, 0, x_pos, height), fill=(255, 255, 255, 6), width=1)
    for offset in range(-240, width, 220):
        draw.line((offset, height, offset + 260, 0), fill=(68, 228, 255, 12), width=1)
    for dot_x, dot_y, radius, fill in ((128, 94, 3, (255, 255, 255, 120)), (1420, 168, 2, (68, 228, 255, 120)), (1340, 780, 3, (138, 125, 255, 120)), (220, 720, 2, (255, 177, 74, 120))):
        draw.ellipse((dot_x - radius, dot_y - radius, dot_x + radius, dot_y + radius), fill=fill)
    return frame


def _darken(image: Image.Image, amount: int) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, amount))
    return Image.alpha_composite(image.convert("RGBA"), overlay)


def _fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    image = image.copy()
    image.thumbnail(size, Image.Resampling.LANCZOS)
    return image


def _map_box(
    box: tuple[int, int, int, int],
    source_size: tuple[int, int],
    target_box: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    src_width, src_height = source_size
    dst_left, dst_top, dst_right, dst_bottom = target_box
    dst_width = dst_right - dst_left
    dst_height = dst_bottom - dst_top
    return (
        dst_left + int(box[0] * dst_width / src_width),
        dst_top + int(box[1] * dst_height / src_height),
        dst_left + int(box[2] * dst_width / src_width),
        dst_top + int(box[3] * dst_height / src_height),
    )


def _center(box: tuple[int, int, int, int]) -> tuple[int, int]:
    return ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)


def _closest_point_on_rect(rect: tuple[int, int, int, int], point: tuple[int, int]) -> tuple[int, int]:
    x = min(max(point[0], rect[0]), rect[2])
    y = min(max(point[1], rect[1]), rect[3])
    candidates = [
        (x, rect[1]),
        (x, rect[3]),
        (rect[0], y),
        (rect[2], y),
    ]
    return min(candidates, key=lambda item: (item[0] - point[0]) ** 2 + (item[1] - point[1]) ** 2)


def _draw_corners(frame: Image.Image, box: tuple[int, int, int, int], accent: str) -> None:
    draw = ImageDraw.Draw(frame)
    rgb = ImageColor.getrgb(accent) + (220,)
    length = 26
    x1, y1, x2, y2 = box
    segments = [
        ((x1, y1), (x1 + length, y1)),
        ((x1, y1), (x1, y1 + length)),
        ((x2, y1), (x2 - length, y1)),
        ((x2, y1), (x2, y1 + length)),
        ((x1, y2), (x1 + length, y2)),
        ((x1, y2), (x1, y2 - length)),
        ((x2, y2), (x2 - length, y2)),
        ((x2, y2), (x2, y2 - length)),
    ]
    for start, end in segments:
        draw.line((start[0], start[1], end[0], end[1]), fill=rgb, width=4)


def _truncate(text: str, length: int) -> str:
    if len(text) <= length:
        return text
    return text[: max(0, length - 3)].rstrip() + "..."


def _cover_resize(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    src_ratio = image.width / image.height
    dst_ratio = size[0] / size[1]
    if src_ratio > dst_ratio:
        new_height = size[1]
        new_width = int(new_height * src_ratio)
    else:
        new_width = size[0]
        new_height = int(new_width / src_ratio)
    resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    left = max(0, (new_width - size[0]) // 2)
    top = max(0, (new_height - size[1]) // 2)
    return resized.crop((left, top, left + size[0], top + size[1]))


def _lerp(start: tuple[float, float], end: tuple[float, float], t: float) -> tuple[float, float]:
    t = max(0.0, min(1.0, _ease(t)))
    return (start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t)


def _ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _select_first(app: ApartmentAgentApp) -> None:
    app.update_idletasks()
    children = app.tree.get_children()
    if not children:
        return
    first = children[0]
    app.tree.selection_set(first)
    app._load_tree_item(first)  # noqa: SLF001
    app.update()
    time.sleep(0.25)


def _capture_window(app: ApartmentAgentApp) -> Image.Image:
    app.update_idletasks()
    left = app.winfo_rootx()
    top = app.winfo_rooty()
    right = left + app.winfo_width()
    bottom = top + app.winfo_height()
    return ImageGrab.grab(bbox=(left, top, right, bottom)).convert("RGB")


def _widget_box(app: ApartmentAgentApp, widget) -> tuple[int, int, int, int]:
    app.update_idletasks()
    root_x = app.winfo_rootx()
    root_y = app.winfo_rooty()
    left = widget.winfo_rootx() - root_x
    top = widget.winfo_rooty() - root_y
    right = left + widget.winfo_width()
    bottom = top + widget.winfo_height()
    return (left, top, right, bottom)


def _encode_video(frames_dir: Path, output_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is required to encode docs/app-explainer.mp4")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-framerate",
            str(FPS),
            "-i",
            str(frames_dir / "frame_%05d.png"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
