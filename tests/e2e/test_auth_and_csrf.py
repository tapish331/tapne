from __future__ import annotations

import re

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from tests.e2e.auth import (
    DEFAULT_DEMO_PASSWORD,
    login_through_modal,
    login_through_page,
    wait_for_authenticated_state,
)
from tests.e2e.data import create_booking_scenario
from tests.e2e.helpers import unique_suffix
from tests.e2e.types import SessionFactory


def _visible_message(page, text: str):
    return page.locator("p.whitespace-pre-wrap:visible").filter(has_text=text).last


@pytest.mark.smoke
def test_navbar_modal_login_then_messages_post_persists_after_reload(session_factory: SessionFactory) -> None:
    """Login via the navbar modal (replacing the retired /login page), then POST a DM
    message and verify it survives a page reload.  This is the primary smoke-level
    CSRF-after-login guard."""
    member = session_factory(name="modal-login-messages-post")
    page = member.page
    message = unique_suffix("smoke-messages")

    page.goto("/")
    page.get_by_role("heading", name="Explore Trips").wait_for()
    login_through_page(page, username="mei")
    page.get_by_role("heading", name="Explore Trips").wait_for()

    page.goto("/messages")
    page.get_by_role("heading", name="Inbox").wait_for()
    page.get_by_role("button", name=re.compile(r"Arun N\.", re.I)).first.click()

    composer = page.locator("input[placeholder='Type a message...']:visible")
    composer.fill(message)
    composer.press("Enter")
    _visible_message(page, message).wait_for()

    page.reload()
    page.get_by_role("button", name=re.compile(r"Arun N\.", re.I)).first.click()
    _visible_message(page, message).wait_for()

    member.audit.assert_clean(ignore_requests=["/frontend-api/home/", "/frontend-api/activity/"])


@pytest.mark.full
def test_modal_login_then_booking_post_persists(session_factory: SessionFactory) -> None:
    scenario = create_booking_scenario(name="modal-login-booking")
    guest = session_factory(name="modal-login-booking")
    page = guest.page
    booking_heading = page.get_by_role("heading", name="Book Your Trip")

    page.goto(f"/trips/{scenario.trip_id}")
    page.get_by_role("heading", name=scenario.title).wait_for()
    page.get_by_role("button", name="Book Now").first.click()
    login_through_modal(page, username=scenario.traveler_username, password=DEFAULT_DEMO_PASSWORD)
    try:
        booking_heading.wait_for(timeout=2_000)
    except PlaywrightTimeoutError:
        page.get_by_role("button", name="Book Now").first.click()
        booking_heading.wait_for()

    page.get_by_role("button", name="Continue").click()
    page.get_by_placeholder("Your full name").fill("Booking Traveler")
    page.get_by_placeholder("you@email.com").fill(f"{scenario.traveler_username}@tapne.local")
    page.get_by_placeholder("+91 9876543210").fill("9876543210")
    page.get_by_role("button", name="Continue").click()
    page.get_by_role("checkbox").click()
    page.get_by_role("button", name="Confirm & Pay").click()

    page.locator("h3:visible").filter(has_text="Booking Confirmed!").wait_for()
    page.get_by_role("button", name="Done").click()

    page.reload()
    page.get_by_role("button", name="Application Pending").wait_for()

    guest.audit.assert_clean()


@pytest.mark.full
def test_signup_modal_creates_an_isolated_account(session_factory: SessionFactory) -> None:
    """Signup via the modal (replacing the retired /signup page)."""
    guest = session_factory(name="signup-modal")
    page = guest.page
    email_prefix = unique_suffix("guardrail-signup")
    email = f"{email_prefix}@example.com"
    password = "GuardrailPass!123"

    page.goto("/")
    page.get_by_role("heading", name="Explore Trips").wait_for()
    page.get_by_role("button", name="Login").first.click()

    login_dialog = page.locator("[role='dialog']").filter(has_text="Welcome back")
    login_dialog.wait_for()
    login_dialog.get_by_role("button", name="Sign up").click()

    signup_dialog = page.locator("[role='dialog']").filter(has_text="Create your account")
    signup_dialog.wait_for()
    signup_dialog.get_by_placeholder("John Doe").fill("Guardrail Signup")
    signup_dialog.get_by_placeholder("you@example.com").fill(email)
    signup_dialog.get_by_placeholder("••••••••").fill(password)
    signup_dialog.get_by_role("button", name="Sign Up").click()
    signup_dialog.wait_for(state="hidden")
    wait_for_authenticated_state(page)

    page.goto("/profile")
    page.get_by_role("heading", name="Guardrail Signup").wait_for()

    guest.audit.assert_clean(ignore_requests=["/frontend-api/home/", "/frontend-api/activity/"])
