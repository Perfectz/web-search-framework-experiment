from __future__ import annotations

from pathlib import Path
from typing import Any

from apartment_agent.utils import ensure_parent


class PlaywrightCapture:
    def __init__(
        self,
        headless: bool = True,
        user_data_dir: str | None = None,
        timeout_ms: int = 30000,
        wait_seconds: float = 2.0,
    ) -> None:
        self.headless = headless
        self.user_data_dir = user_data_dir
        self.timeout_ms = timeout_ms
        self.wait_seconds = wait_seconds

    def capture(self, url: str, output_path: str | Path) -> Path | None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "Playwright is not installed. Run `pip install -r requirements-optional.txt` and `playwright install chromium`."
            ) from exc

        output = ensure_parent(output_path)
        with sync_playwright() as playwright:  # pragma: no cover - requires browser runtime
            page, close_target = self._open_page(playwright)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                page.wait_for_timeout(int(self.wait_seconds * 1000))
                page.screenshot(path=str(output), full_page=True)
            finally:
                close_target.close()
        return output

    def snapshot(self, url: str, include_links: bool = True) -> dict[str, Any]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "Playwright is not installed. Run `pip install -r requirements-optional.txt` and `playwright install chromium`."
            ) from exc

        with sync_playwright() as playwright:  # pragma: no cover - requires browser runtime
            page, close_target = self._open_page(playwright)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                page.wait_for_timeout(int(self.wait_seconds * 1000))
                title = page.title()
                html = page.content()
                text = page.locator("body").inner_text() if page.locator("body").count() else ""
                links: list[dict[str, str]] = []
                if include_links:
                    links = page.eval_on_selector_all(
                        "a[href]",
                        """
                        (anchors) => anchors.map((anchor) => ({
                          href: anchor.href || "",
                          text: (anchor.innerText || anchor.textContent || "").trim()
                        }))
                        """,
                    )
                if "Just a moment" in title:
                    raise RuntimeError(
                        "Browser was blocked by Hipflat's Cloudflare challenge. Use a verified Playwright profile via `--profile-dir` or set `APARTMENT_AGENT_BROWSER_PROFILE_DIR` and run headful once."
                    )
                return {
                    "url": page.url,
                    "title": title,
                    "html": html,
                    "text": text,
                    "links": links,
                }
            except Exception:
                close_target.close()
                raise

    def fetch_html(self, url: str) -> str:
        snapshot = self.snapshot(url, include_links=False)
        return str(snapshot["html"])

    def fetch_text(self, url: str) -> str:
        snapshot = self.snapshot(url, include_links=False)
        return str(snapshot["text"])

    def _open_page(self, playwright: Any) -> tuple[Any, Any]:
        if self.user_data_dir:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=self.headless,
                locale="en-US",
            )
            page = context.pages[0] if context.pages else context.new_page()
            return page, context

        browser = playwright.chromium.launch(headless=self.headless)
        context = browser.new_context(locale="en-US")
        page = context.new_page()
        return page, browser
