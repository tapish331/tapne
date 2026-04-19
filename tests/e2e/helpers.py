from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, cast

from playwright.sync_api import ConsoleMessage, Page, Request, Response


def _string_list() -> list[str]:
    return []


def sanitize_name(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-").lower()
    return slug or "artifact"


def unique_suffix(prefix: str) -> str:
    return f"{prefix}-{int(time.time() * 1000)}"


def future_trip_window(*, starts_in_days: int = 21, duration_days: int = 4, close_days_before: int = 7) -> tuple[str, str, str]:
    start_date = date.today() + timedelta(days=starts_in_days)
    end_date = start_date + timedelta(days=duration_days)
    close_date = start_date - timedelta(days=close_days_before)
    return start_date.isoformat(), end_date.isoformat(), close_date.isoformat()


def fill_trip_basics(
    page: Page,
    *,
    title: str,
    summary: str,
    destination: str,
    category: str = "Backpacking",
    total_seats: str = "8",
    total_price: str = "18000",
    starts_at: str,
    ends_at: str,
    booking_closes_at: str,
) -> None:
    page.locator("input[placeholder='e.g. Spiti Valley Road Trip']").fill(title)
    page.locator("textarea[placeholder*='A thrilling road trip']").fill(summary)
    page.locator("input[placeholder='e.g. Manali, Himachal']").fill(destination)

    page.get_by_role("combobox").first.click()
    page.get_by_role("option", name=category).click()

    date_inputs = page.locator("input[type='date']")
    date_inputs.nth(0).fill(starts_at)
    date_inputs.nth(1).fill(ends_at)
    date_inputs.nth(2).fill(booking_closes_at)

    page.locator("input[placeholder='12']").fill(total_seats)
    page.locator("input[placeholder='25000']").fill(total_price)


def fill_rich_text_editor(page: Page, text: str, *, index: int = 0, replace: bool = False) -> None:
    editor = page.locator(".tiptap").nth(index)
    editor.click()
    if replace:
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
    page.keyboard.type(text)


@dataclass
class BrowserAudit:
    page: Page
    artifact_dir: Path
    console_errors: list[str] = field(default_factory=_string_list)
    page_errors: list[str] = field(default_factory=_string_list)
    request_failures: list[str] = field(default_factory=_string_list)
    bad_responses: list[str] = field(default_factory=_string_list)

    def __post_init__(self) -> None:
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.page.on("console", self._handle_console)
        self.page.on("pageerror", self._handle_page_error)
        self.page.on("requestfailed", self._handle_request_failed)
        self.page.on("response", self._handle_response)

    def _handle_console(self, message: ConsoleMessage) -> None:
        if message.type != "error":
            return
        text = message.text.strip()
        if not text:
            return
        if "favicon" in text.lower():
            return
        self.console_errors.append(text)

    def _handle_page_error(self, error: BaseException) -> None:
        self.page_errors.append(str(error))

    def _handle_request_failed(self, request: Request) -> None:
        resource_type = request.resource_type or ""
        if resource_type not in {"document", "fetch", "xhr"}:
            return
        raw_failure = cast(dict[str, Any] | str | None, request.failure)
        if isinstance(raw_failure, dict):
            reason = str(raw_failure.get("errorText") or "requestfailed")
        elif isinstance(raw_failure, str):
            reason = raw_failure
        else:
            reason = "requestfailed"
        # Chromium reports in-flight fetches aborted by page navigation as request failures.
        if "ERR_ABORTED" in reason:
            return
        self.request_failures.append(f"{resource_type} {request.method} {request.url} :: {reason}")

    def _handle_response(self, response: Response) -> None:
        resource_type = response.request.resource_type or ""
        if resource_type not in {"fetch", "xhr"}:
            return
        if response.status < 400:
            return
        self.bad_responses.append(
            f"{resource_type} {response.request.method} {response.url} :: {response.status}"
        )

    def assert_clean(
        self,
        *,
        ignore_console: Iterable[str] = (),
        ignore_requests: Iterable[str] = (),
        ignore_responses: Iterable[str] = (),
    ) -> None:
        console_errors: list[str] = self._filter(self.console_errors, ignore_console)
        page_errors: list[str] = list(self.page_errors)
        request_failures: list[str] = self._filter(self.request_failures, ignore_requests)
        bad_responses: list[str] = self._filter(self.bad_responses, ignore_responses)
        problems = [
            *[f"console: {item}" for item in console_errors],
            *[f"pageerror: {item}" for item in page_errors],
            *[f"requestfailed: {item}" for item in request_failures],
            *[f"bad-response: {item}" for item in bad_responses],
        ]
        if not problems:
            return

        screenshot_path = self.artifact_dir / "failure.png"
        html_path = self.artifact_dir / "page.html"
        self.page.screenshot(path=str(screenshot_path), full_page=True)
        html_path.write_text(self.page.content(), encoding="utf-8")
        rendered = "\n".join(f"- {item}" for item in problems)
        raise AssertionError(f"Browser audit failed:\n{rendered}")

    @staticmethod
    def _filter(values: list[str], ignore_patterns: Iterable[str]) -> list[str]:
        patterns = [pattern for pattern in ignore_patterns if pattern]
        if not patterns:
            return list(values)
        filtered: list[str] = []
        for value in values:
            if any(pattern in value for pattern in patterns):
                continue
            filtered.append(value)
        return filtered
