from __future__ import annotations

import re

import pytest

from tests.e2e.data import create_manage_trip_scenario
from tests.e2e.helpers import unique_suffix
from tests.e2e.types import SessionFactory


def _visible_message(page, text: str):
    return page.locator("p.whitespace-pre-wrap:visible").filter(has_text=text).last


@pytest.mark.full
def test_manage_trip_booking_status_and_cancel_persist(session_factory: SessionFactory) -> None:
    scenario = create_manage_trip_scenario(name="manage-status")
    host = session_factory(name="manage-status-host", username=scenario.host_username)
    page = host.page

    page.goto(f"/manage-trip/{scenario.trip_id}")
    page.get_by_role("heading", name=scenario.title).wait_for()

    page.get_by_role("button", name="Close Bookings").click()
    page.get_by_role("button", name="Reopen Bookings").wait_for()

    page.reload()
    page.get_by_role("button", name="Reopen Bookings").wait_for()
    page.get_by_role("button", name="Reopen Bookings").click()
    page.get_by_role("button", name="Close Bookings").wait_for()

    page.reload()
    page.get_by_role("button", name="Close Bookings").wait_for()
    page.get_by_role("button", name="Cancel Trip").click()
    page.get_by_placeholder("Reason for cancellation (required)").fill("Guardrail cancellation flow.")
    page.get_by_role("button", name="Confirm Cancel").click()
    page.get_by_text("Cancelled").first.wait_for()

    page.reload()
    page.get_by_text("Cancelled").first.wait_for()
    assert page.get_by_role("button", name="Cancel Trip").count() == 0

    host.audit.assert_clean()


@pytest.mark.full
def test_manage_trip_approve_message_and_remove_flows_persist(session_factory: SessionFactory) -> None:
    scenario = create_manage_trip_scenario(name="manage-participants")
    host = session_factory(name="manage-participants-host", username=scenario.host_username)
    participant = session_factory(name="manage-participants-member", username=scenario.participant_username)
    page = host.page
    message = unique_suffix("manage-message")

    page.goto(f"/manage-trip/{scenario.trip_id}")
    page.get_by_role("heading", name=scenario.title).wait_for()
    page.get_by_role("tab", name=re.compile("^Applications")).click()
    page.get_by_role("button", name="Approve", exact=True).click()

    page.reload()
    page.get_by_role("tab", name=re.compile("^Applications")).click()
    page.get_by_role("button", name=re.compile("approved", re.I)).click()
    page.get_by_text(scenario.pending_display_name).wait_for()

    page.get_by_role("tab", name=re.compile("^Participants")).click()
    page.get_by_role("button", name="Message All").click()
    page.get_by_placeholder("Type your message...").fill(message)
    page.get_by_role("button", name="Send Message").click()

    participant.page.goto(f"/inbox?dm={scenario.host_username}")
    participant.page.get_by_role("heading", name="Inbox").wait_for()
    _visible_message(participant.page, message).wait_for()

    participant_card = (
        page.locator("div.flex.items-center.gap-3.p-4")
        .filter(has_text=scenario.participant_display_name)
        .filter(has_text="Confirmed")
        .first
    )
    participant_card.get_by_role("button").click()
    page.get_by_role("button", name="Remove").click()

    page.reload()
    assert page.get_by_text(scenario.participant_display_name).count() == 0

    participant.page.goto(f"/trips/{scenario.trip_id}")
    participant.page.get_by_role("heading", name=scenario.title).wait_for()
    participant.page.get_by_role("button", name="Book Now").wait_for()

    host.audit.assert_clean()
    participant.audit.assert_clean()
