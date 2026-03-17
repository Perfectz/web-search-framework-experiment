from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageGrab

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apartment_agent.gui import ApartmentAgentApp

DOCS_DIR = ROOT / "docs"
SOURCE_DB = ROOT / "data" / "apartment_agent.sqlite"
CRITERIA_PATH = ROOT / "config" / "criteria.json"
SOURCES_PATH = ROOT / "config" / "sources.json"
OUTPUTS_PATH = ROOT / "outputs"
GIF_PATH = DOCS_DIR / "app-demo.gif"
SCREENSHOT_PATH = DOCS_DIR / "app-overview.png"


def main() -> None:
    if not SOURCE_DB.exists():
        raise SystemExit(f"Missing database: {SOURCE_DB}")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
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
            app.geometry("1560x860+30+30")
            app.update()
            time.sleep(0.4)

            frames: list[Image.Image] = []
            durations: list[int] = []

            _select_first(app)
            first_capture = _capture_window(app)
            first_capture.save(SCREENSHOT_PATH, format="PNG")
            frames.append(_captioned(first_capture, "Browse scored listings and inspect agent contact details"))
            durations.append(1400)

            app.filter_var.set("alert")
            app.refresh_results()
            _select_first(app)
            frames.append(_captioned(_capture_window(app), "Filter to strongest matches"))
            durations.append(1200)

            app.search_var.set("Harmony")
            app.refresh_results()
            _select_first(app)
            frames.append(_captioned(_capture_window(app), "Search by project name or listing text"))
            durations.append(1200)

            if app.selected_listing:
                app.set_contacted(True)
            frames.append(_captioned(_capture_window(app), "Mark a listing as contacted and keep that state in SQLite"))
            durations.append(1200)

            app.notebook.select(app.email_tab)
            app.regenerate_draft()
            frames.append(_captioned(_capture_window(app), "Generate an outreach email and open it in Gmail from the app"))
            durations.append(1800)

            _save_gif(frames, durations, GIF_PATH)
            print(GIF_PATH)
            print(SCREENSHOT_PATH)
        finally:
            app.destroy()


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
    return ImageGrab.grab(bbox=(left, top, right, bottom))


def _captioned(image: Image.Image, caption: str) -> Image.Image:
    width, height = image.size
    band_height = 72
    canvas = Image.new("RGB", (width, height + band_height), "#0f172a")
    canvas.paste(image, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, height, width, height + band_height), fill="#0f172a")
    font = _load_font(28)
    draw.text((24, height + 20), caption, fill="#f8fafc", font=font)
    return canvas.resize((1180, int((height + band_height) * 1180 / width)))


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _save_gif(frames: list[Image.Image], durations: list[int], path: Path) -> None:
    palette_frames = [frame.convert("P", palette=Image.ADAPTIVE) for frame in frames]
    palette_frames[0].save(
        path,
        save_all=True,
        append_images=palette_frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )


if __name__ == "__main__":
    main()
