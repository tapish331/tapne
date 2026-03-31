#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Create a Playwright storage_state file for authenticated visual audits.

This script logs into Tapne through the user-facing auth modal and saves
session cookies/local storage for reuse with crawl_and_capture.py.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import os
from pathlib import Path
from typing import Any, Callable, cast
from urllib.parse import urlsplit

PlaywrightFactory = Callable[[], Any]

PlaywrightError: type[Exception] = Exception
PlaywrightTimeoutError: type[Exception] = Exception
async_playwright: PlaywrightFactory | None = None
playwright_import_error: Exception | None = None
playwright_module: object | None = None
try:
    playwright_module = importlib.import_module("playwright.async_api")
except ImportError as exc:  # pragma: no cover - environment dependent
    playwright_import_error = exc
else:
    imported_playwright_error: object = getattr(playwright_module, "Error", Exception)
    imported_timeout_error: object = getattr(playwright_module, "TimeoutError", Exception)
    imported_async_playwright: object = getattr(playwright_module, "async_playwright", None)
    if isinstance(imported_playwright_error, type) and issubclass(imported_playwright_error, Exception):
        PlaywrightError = imported_playwright_error
    if isinstance(imported_timeout_error, type) and issubclass(imported_timeout_error, Exception):
        PlaywrightTimeoutError = imported_timeout_error
    if callable(imported_async_playwright):
        async_playwright = cast(PlaywrightFactory, imported_async_playwright)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Authenticate and save Playwright storage_state JSON."
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("BASE_URL", "http://localhost:8000"),
        help="Site root URL (default: BASE_URL env or http://localhost:8000).",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("TAPNE_AUDIT_USERNAME", ""),
        help="Login username/email (or set TAPNE_AUDIT_USERNAME).",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("TAPNE_AUDIT_PASSWORD", ""),
        help="Login password (or set TAPNE_AUDIT_PASSWORD).",
    )
    parser.add_argument(
        "--output",
        default="artifacts/auth/admin-storage-state.json",
        help="Output storage state JSON path.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=30000,
        help="Navigation/action timeout in milliseconds.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run with browser window visible for debugging.",
    )
    return parser.parse_args()


def normalize_base_url(raw: str) -> str:
    value = raw.strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("--base-url must be a valid http/https URL.")
    return value.rstrip("/")


def ensure_credentials(username: str, password: str) -> tuple[str, str]:
    user = username.strip()
    secret = password
    if not user:
        raise ValueError("Missing username. Pass --username or TAPNE_AUDIT_USERNAME.")
    if not secret:
        raise ValueError("Missing password. Pass --password or TAPNE_AUDIT_PASSWORD.")
    return user, secret


async def wait_for_logged_in_state(page: Any, timeout_ms: int) -> bool:
    checks = [
        "html[data-user-state='member']",
        "a[href='/accounts/me/']",
        "form[action='/accounts/logout/'] button",
    ]
    for selector in checks:
        try:
            await page.wait_for_selector(selector, timeout=timeout_ms)
            return True
        except PlaywrightTimeoutError:
            continue
    return False


async def create_storage_state(
    base_url: str,
    username: str,
    password: str,
    output_path: Path,
    timeout_ms: int,
    headed: bool,
) -> int:
    if async_playwright is None:
        print("Missing dependency: playwright")
        print("Install with:")
        print(
            "  python -m pip install -r "
            "skills/webpage-visual-perfection-audit/requirements.txt"
        )
        print("  python -m playwright install chromium")
        if playwright_import_error:
            print(f"Import error: {playwright_import_error}")
        return 2
    playwright_factory = async_playwright

    output_path.parent.mkdir(parents=True, exist_ok=True)

    async with playwright_factory() as p:
        browser = await p.chromium.launch(headless=not headed)
        context = await browser.new_context(
            viewport={"width": 1366, "height": 900},
        )
        page = await context.new_page()
        page.set_default_timeout(timeout_ms)

        try:
            await page.goto(base_url, wait_until="domcontentloaded")
            await page.wait_for_load_state("networkidle")

            if await wait_for_logged_in_state(page, timeout_ms=1500):
                print("[info] Existing logged-in session detected. Saving state.")
            else:
                login_button = page.locator(
                    "[data-modal-open='auth'][data-auth-mode='login']"
                ).first
                await login_button.click()

                login_form = page.locator("form[action='/accounts/login/']").first
                await login_form.wait_for(state="visible", timeout=timeout_ms)

                await login_form.locator("input[name='username']").fill(username)
                await login_form.locator("input[name='password']").fill(password)
                await login_form.locator("button[type='submit']").click()

                await page.wait_for_load_state("networkidle")
                success = await wait_for_logged_in_state(page, timeout_ms=timeout_ms)
                if not success:
                    # Some flows redirect with modal error query params.
                    current_url = page.url
                    fail_shot = output_path.with_suffix(".login-failed.png")
                    await page.screenshot(path=str(fail_shot), full_page=True)
                    print(f"[error] Login did not reach authenticated state. URL={current_url}")
                    print(f"[error] Failure screenshot: {fail_shot}")
                    return 1

            await context.storage_state(path=str(output_path))
            print(f"[done] Storage state saved: {output_path}")
            print(
                "[next] Use with crawl_and_capture.py --storage-state "
                f"\"{output_path}\""
            )
            return 0
        except PlaywrightError as exc:
            print(f"[error] Playwright failed: {exc}")
            return 1
        finally:
            await context.close()
            await browser.close()


def main() -> int:
    args = parse_args()
    try:
        base_url = normalize_base_url(args.base_url)
        username, password = ensure_credentials(args.username, args.password)
        output_path = Path(args.output).resolve()
        return asyncio.run(
            create_storage_state(
                base_url=base_url,
                username=username,
                password=password,
                output_path=output_path,
                timeout_ms=args.timeout_ms,
                headed=args.headed,
            )
        )
    except KeyboardInterrupt:
        print("Interrupted.")
        return 130
    except Exception as exc:
        print(f"[error] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
