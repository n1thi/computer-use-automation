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
from src.surface.models import ObservedElement, PageObservation


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
                return self._page.get_by_role(
                    target.role,
                    name=self._pattern(target.name),
                )
            return self._page.get_by_role(target.role)

        if target.label:
            return self._page.get_by_label(self._pattern(target.label))

        if target.text:
            return self._page.get_by_text(target.text, exact=True)

        if target.stable_attribute:
            selector = "".join(
                f'[{key}="{value}"]'
                for key, value in target.stable_attribute.items()
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

    def observe(
        self,
        max_text_chars: int = 5000,
        max_elements: int = 50,
    ) -> PageObservation:
        try:
            visible_text = self._page.locator("body").inner_text(timeout=3000)
        except Exception:
            visible_text = ""

        visible_text = visible_text[:max_text_chars]

        raw_elements = self._page.evaluate(
            """
            (maxElements) => {
              function isVisible(el) {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return (
                  style.visibility !== "hidden" &&
                  style.display !== "none" &&
                  rect.width > 0 &&
                  rect.height > 0
                );
              }

              function labelFor(el) {
                if (el.id) {
                  const explicit = document.querySelector(
                    `label[for="${CSS.escape(el.id)}"]`
                  );
                  if (explicit) return explicit.innerText.trim();
                }

                const parentLabel = el.closest("label");
                if (parentLabel) return parentLabel.innerText.trim();

                return null;
              }

              function inferredRole(el) {
                const explicit = el.getAttribute("role");
                if (explicit) return explicit;

                const tag = el.tagName.toLowerCase();
                if (tag === "button") return "button";
                if (tag === "a" && el.getAttribute("href")) return "link";
                if (tag === "textarea") return "textbox";
                if (tag === "select") return "combobox";

                if (tag === "input") {
                  const type = (el.getAttribute("type") || "text").toLowerCase();
                  if (type === "radio") return "radio";
                  if (type === "checkbox") return "checkbox";
                  if (["submit", "button", "reset"].includes(type)) return "button";
                  return "textbox";
                }

                return null;
              }

              function accessibleName(el, label, text) {
                return (
                  el.getAttribute("aria-label") ||
                  label ||
                  el.getAttribute("placeholder") ||
                  el.getAttribute("title") ||
                  text ||
                  el.getAttribute("name") ||
                  null
                );
              }

              const selector = [
                "a[href]",
                "button",
                "input",
                "select",
                "textarea",
                "[role]"
              ].join(",");

              return Array.from(document.querySelectorAll(selector))
                .filter(isVisible)
                .slice(0, maxElements)
                .map((el, index) => {
                  const tag = el.tagName.toLowerCase();
                  const text = (el.innerText || "").trim() || null;
                  const label = labelFor(el);
                  const role = inferredRole(el);

                  return {
                    index,
                    tag,
                    role,
                    name: accessibleName(el, label, text),
                    label,
                    text,
                    input_type:
                      tag === "input"
                        ? (el.getAttribute("type") || "text").toLowerCase()
                        : null,
                    checked:
                      (tag === "input" &&
                       ["checkbox", "radio"].includes(
                         (el.getAttribute("type") || "").toLowerCase()
                       ))
                        ? Boolean(el.checked)
                        : null,
                    disabled: Boolean(el.disabled)
                  };
                });
            }
            """,
            max_elements,
        )

        elements = [ObservedElement.model_validate(item) for item in raw_elements]

        return PageObservation(
            url=self._page.url,
            title=self._page.title(),
            visible_text=visible_text,
            interactive_elements=elements,
        )

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
