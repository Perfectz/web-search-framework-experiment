from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import render_explainer_video as explainer

GIF_PATH = explainer.DOCS_DIR / "app-linkedin-showcase.gif"
POSTER_PATH = explainer.DOCS_DIR / "app-linkedin-showcase-poster.png"
FRAME_SIZE = (1200, 675)
FPS = 12
HOLD_SECONDS = 1.15
TRANSITION_SECONDS = 0.35


def main() -> None:
    assets = explainer._capture_assets()  # noqa: SLF001
    screens = _build_screens(assets)
    frames = _render_frames(screens)
    _save_gif(frames, GIF_PATH)
    frames[0].save(POSTER_PATH, format="PNG")
    print(GIF_PATH)
    print(POSTER_PATH)


def _build_screens(assets: dict[str, object]) -> list[Image.Image]:
    listing_browser = explainer._browser(  # noqa: SLF001
        assets["listing_page"],
        str(assets["listing_url"]),
        str(assets["listing_title"]),
    ).convert("RGB")
    gmail_browser = explainer._browser(  # noqa: SLF001
        assets["gmail_browser"],
        str(assets["gmail_url"]),
        "Gmail Draft",
    ).convert("RGB")
    return [
        assets["overview"].convert("RGB"),
        assets["triage"].convert("RGB"),
        listing_browser,
        gmail_browser,
    ]


def _render_frames(screens: list[Image.Image]) -> list[Image.Image]:
    frames: list[Image.Image] = []
    hold_frames = max(1, int(round(HOLD_SECONDS * FPS)))
    transition_frames = max(1, int(round(TRANSITION_SECONDS * FPS)))

    prepared = [_screen_card(screen, index) for index, screen in enumerate(screens)]

    for index, screen in enumerate(prepared):
        for hold_index in range(hold_frames):
            progress = hold_index / max(1, hold_frames - 1)
            frames.append(_compose_frame(screen, index, progress))

        next_screen = prepared[(index + 1) % len(prepared)]
        for transition_index in range(transition_frames):
            progress = transition_index / max(1, transition_frames - 1)
            frames.append(_crossfade(screen, next_screen, progress))

    return frames


def _screen_card(screen: Image.Image, index: int) -> Image.Image:
    canvas = _background(index)
    motion = 0.965 + 0.025 * (index % 3)
    fitted = explainer._fit(screen.convert("RGBA"), (1040, 580))  # noqa: SLF001
    width = max(1, int(fitted.width * motion))
    height = max(1, int(fitted.height * motion))
    fitted = fitted.resize((width, height), Image.Resampling.LANCZOS)

    frame = Image.new("RGBA", FRAME_SIZE, (0, 0, 0, 0))
    card_w = fitted.width + 46
    card_h = fitted.height + 46
    left = (FRAME_SIZE[0] - card_w) // 2
    top = (FRAME_SIZE[1] - card_h) // 2

    shadow = Image.new("RGBA", FRAME_SIZE, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle((left + 14, top + 18, left + card_w + 14, top + card_h + 18), radius=34, fill=(3, 8, 20, 100))
    shadow_draw.rounded_rectangle((left + 8, top + 10, left + card_w + 8, top + card_h + 10), radius=34, fill=(3, 8, 20, 70))
    frame.alpha_composite(shadow)

    card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    card_draw = ImageDraw.Draw(card)
    card_draw.rounded_rectangle((0, 0, card_w - 1, card_h - 1), radius=30, fill=(248, 250, 255, 255), outline=(217, 229, 255, 255), width=2)
    card_draw.rounded_rectangle((12, 12, card_w - 13, card_h - 13), radius=24, outline=(255, 255, 255, 180), width=1)
    card.alpha_composite(fitted, (23, 23))
    frame.alpha_composite(card, (left, top))

    glow = Image.new("RGBA", FRAME_SIZE, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    accent = [(68, 228, 255), (55, 240, 194), (138, 125, 255), (255, 177, 74), (68, 179, 255)][index % 5]
    for spread, alpha in ((26, 24), (18, 32), (10, 44)):
        glow_draw.rounded_rectangle((left - spread, top - spread, left + card_w + spread, top + card_h + spread), radius=38, outline=accent + (alpha,), width=2)
    frame.alpha_composite(glow)

    return Image.alpha_composite(canvas, frame).convert("RGB")


def _compose_frame(screen: Image.Image, index: int, progress: float) -> Image.Image:
    zoom = 1.0 + 0.018 * math.sin(progress * math.pi)
    drift_x = int(math.sin(progress * math.pi * 1.2 + index * 0.7) * 8)
    drift_y = int(math.cos(progress * math.pi + index * 0.4) * 6)
    working = screen.convert("RGBA")
    resized = working.resize(
        (int(working.width * zoom), int(working.height * zoom)),
        Image.Resampling.LANCZOS,
    )
    left = (resized.width - FRAME_SIZE[0]) // 2 - drift_x
    top = (resized.height - FRAME_SIZE[1]) // 2 - drift_y
    return resized.crop((left, top, left + FRAME_SIZE[0], top + FRAME_SIZE[1])).convert("RGB")


def _crossfade(current: Image.Image, nxt: Image.Image, progress: float) -> Image.Image:
    current_frame = _compose_frame(current, 0, 1.0)
    next_frame = _compose_frame(nxt, 1, progress)
    return Image.blend(current_frame, next_frame, progress)


def _background(index: int) -> Image.Image:
    colors = [
        ((5, 10, 22), (10, 26, 52), (0, 168, 255, 66)),
        ((6, 11, 24), (9, 34, 56), (0, 225, 188, 54)),
        ((7, 10, 22), (22, 24, 58), (79, 70, 229, 62)),
        ((8, 10, 24), (31, 24, 62), (255, 177, 74, 42)),
        ((5, 10, 22), (16, 22, 54), (68, 179, 255, 58)),
    ]
    top_rgb, bottom_rgb, glow_rgb = colors[index % len(colors)]
    image = Image.new("RGBA", FRAME_SIZE, (0, 0, 0, 255))
    draw = ImageDraw.Draw(image)
    for y in range(FRAME_SIZE[1]):
        blend = y / max(1, FRAME_SIZE[1] - 1)
        color = tuple(int(top_rgb[i] * (1.0 - blend) + bottom_rgb[i] * blend) for i in range(3))
        draw.line((0, y, FRAME_SIZE[0], y), fill=color + (255,))

    overlay = Image.new("RGBA", FRAME_SIZE, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    for x in range(0, FRAME_SIZE[0], 80):
        overlay_draw.line((x, 0, x, FRAME_SIZE[1]), fill=(255, 255, 255, 12), width=1)
    for y in range(0, FRAME_SIZE[1], 80):
        overlay_draw.line((0, y, FRAME_SIZE[0], y), fill=(255, 255, 255, 12), width=1)
    for offset in range(-260, FRAME_SIZE[0], 240):
        overlay_draw.line((offset, FRAME_SIZE[1], offset + 260, 0), fill=(68, 228, 255, 16), width=1)
    overlay_draw.ellipse((20, 360, 420, 760), fill=glow_rgb)
    overlay_draw.ellipse((780, 40, 1260, 520), fill=(glow_rgb[0], glow_rgb[1], glow_rgb[2], max(26, glow_rgb[3] - 12)))
    image = Image.alpha_composite(image, overlay)
    return image


def _save_gif(frames: list[Image.Image], path: Path) -> None:
    duration = int(round(1000 / FPS))
    palette_frames = [frame.convert("P", palette=Image.ADAPTIVE, colors=255) for frame in frames]
    palette_frames[0].save(
        path,
        save_all=True,
        append_images=palette_frames[1:],
        duration=duration,
        loop=0,
        optimize=True,
        disposal=2,
    )


if __name__ == "__main__":
    main()
