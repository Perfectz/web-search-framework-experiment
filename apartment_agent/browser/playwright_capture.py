from __future__ import annotations

from pathlib import Path

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
            if self.user_data_dir:
                context = playwright.chromium.launch_persistent_context(
                    user_data_dir=self.user_data_dir,
                    headless=self.headless,
                    locale="en-US",
                )
                page = context.pages[0] if context.pages else context.new_page()
                close_target = context
            else:
                browser = playwright.chromium.launch(headless=self.headless)
                context = browser.new_context(locale="en-US")
                page = context.new_page()
                close_target = browser

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                page.wait_for_timeout(int(self.wait_seconds * 1000))
                page.screenshot(path=str(output), full_page=True)
            finally:
                close_target.close()
        return output
