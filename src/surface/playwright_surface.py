from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from src.artifact.models import Target
from src.surface.base import Surface


class PlaywrightSurface(Surface):
    """Browser implementation of the generic Surface contract."""

    def __init__(self, headless: bool = True) -> None:
        self._playwright: Playwright = sync_playwright().start()
        self._browser: Browser = self._playwright.chromium.launch(headless=headless)
        self._context: BrowserContext = self._browser.new_context()
        self._page: Page = self._context.new_page()

    def _pattern(self, value: str) -> re.Pattern[str]:
        return re.compile(rf"^{re.escape(value)}$", re.IGNORECASE)

    def _locator(self, target: Target) -> Locator:
        if target.role:
            if target.name:
                return self._page.get_by_role(target.role, name=self._pattern(target.name))
            return self._page.get_by_role(target.role)

        if target.label:
            return self._page.get_by_label(self._pattern(target.label))

        if target.text:
            return self._page.get_by_text(target.text, exact=True)

        if target.stable_attribute:
            selector = "".join(
                f'[{key}="{value}"]' for key, value in target.stable_attribute.items()
            )
            return self._page.locator(selector)

        if target.css:
            return self._page.locator(target.css)

        if target.xpath:
            return self._page.locator(f"xpath={target.xpath}")

        if target.name:
            return self._page.get_by_text(self._pattern(target.name))

        raise ValueError(f"Unable to resolve target: {target.model_dump()}")

    def open(self, url: str) -> None:
        self._page.goto(url, wait_until="domcontentloaded")

    def click(self, target: Target, timeout_ms: int = 5000) -> None:
        self._locator(target).first.click(timeout=timeout_ms)

    def type(self, target: Target, value: str, timeout_ms: int = 5000) -> None:
        self._locator(target).first.fill(value, timeout=timeout_ms)

    def select(self, target: Target, value: str, timeout_ms: int = 5000) -> None:
        locator = self._locator(target).first
        locator.wait_for(state="visible", timeout=timeout_ms)
        try:
            locator.select_option(value=value, timeout=timeout_ms)
        except Exception:
            locator.select_option(label=value, timeout=timeout_ms)

    def read(self, target: Target, timeout_ms: int = 5000) -> str:
        locator = self._locator(target).first
        locator.wait_for(state="visible", timeout=timeout_ms)
        return locator.inner_text(timeout=timeout_ms)

    def screenshot(self, path: str | Path) -> str:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        self._page.screenshot(path=str(output), full_page=True)
        return str(output)

    def is_visible(self, target: Target, timeout_ms: int = 1000) -> bool:
        locator = self._locator(target).first
        try:
            locator.wait_for(state="visible", timeout=timeout_ms)
            return True
        except PlaywrightTimeoutError:
            return False

    def wait(self, timeout_ms: int) -> None:
        self._page.wait_for_timeout(timeout_ms)

    @property
    def current_url(self) -> str:
        return self._page.url

    def close(self) -> None:
        self._context.close()
        self._browser.close()
        self._playwright.stop()
