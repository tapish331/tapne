from __future__ import annotations

import os
import re
from pathlib import Path

from playwright.sync_api import Browser, Page


DEFAULT_DEMO_PASSWORD = os.getenv("TAPNE_DEMO_PASSWORD", "TapneDemoPass!123")


def user_email(username_or_email: str) -> str:
    raw = username_or_email.strip()
    if "@" in raw:
        return raw
    return f"{raw}@tapne.local"


def wait_for_authenticated_state(page: Page) -> None:
    page.wait_for_function(
        """
        () => {
          const raw = window.localStorage.getItem("auth-storage");
          if (!raw) return false;
          try {
            return Boolean(JSON.parse(raw)?.state?.user?.username);
          } catch {
            return false;
          }
        }
        """
    )


def _session_matches_username(page: Page, *, username: str) -> bool:
    payload = page.evaluate(
        """
        async () => {
          try {
            const response = await fetch("/frontend-api/session/", {
              credentials: "include",
              headers: { Accept: "application/json" },
            });
            const json = await response.json();
            return {
              ok: response.ok,
              authenticated: Boolean(json?.authenticated),
              username: String(json?.user?.username || ""),
            };
          } catch (error) {
            return {
              ok: false,
              authenticated: false,
              username: "",
              error: String(error),
            };
          }
        }
        """
    )
    return bool(payload.get("ok")) and bool(payload.get("authenticated")) and payload.get("username") == username


def _storage_state_is_valid(
    browser: Browser,
    *,
    base_url: str,
    storage_path: Path,
    username: str,
) -> bool:
    context = browser.new_context(
        base_url=base_url,
        viewport={"width": 1440, "height": 900},
        storage_state=str(storage_path),
    )
    page = context.new_page()
    try:
        page.goto(f"{base_url}/", wait_until="load")
        return _session_matches_username(page, username=username)
    finally:
        context.close()


def ensure_storage_state(
    browser: Browser,
    *,
    base_url: str,
    auth_dir: Path,
    username: str,
    password: str = DEFAULT_DEMO_PASSWORD,
    refresh: bool = False,
) -> Path:
    auth_dir.mkdir(parents=True, exist_ok=True)
    storage_path = auth_dir / f"{username}.storage-state.json"
    if storage_path.exists() and not refresh:
        if _storage_state_is_valid(
            browser,
            base_url=base_url,
            storage_path=storage_path,
            username=username,
        ):
            return storage_path

    context = browser.new_context(base_url=base_url, viewport={"width": 1440, "height": 900})
    page = context.new_page()
    try:
        page.goto(f"{base_url}/login", wait_until="load")
        login_through_page(page, username=username, password=password)
        page.wait_for_url(re.compile(rf"{re.escape(base_url)}/?$"))
        wait_for_authenticated_state(page)
        assert _session_matches_username(page, username=username)
        context.storage_state(path=str(storage_path))
        return storage_path
    finally:
        context.close()


def login_through_page(page: Page, *, username: str, password: str = DEFAULT_DEMO_PASSWORD) -> None:
    page.locator("input[type='email']").fill(user_email(username))
    page.locator("input[type='password']").fill(password)
    page.get_by_role("button", name="Log In").click()
    wait_for_authenticated_state(page)


def login_through_modal(page: Page, *, username: str, password: str = DEFAULT_DEMO_PASSWORD) -> None:
    dialog = page.locator("[role='dialog']").filter(has_text="Welcome back")
    dialog.wait_for()
    dialog.get_by_placeholder("username or email").fill(username)
    dialog.get_by_placeholder("••••••••").fill(password)
    dialog.get_by_role("button", name="Log In").click()
    dialog.wait_for(state="hidden")
    wait_for_authenticated_state(page)
