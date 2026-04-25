from __future__ import annotations

import re
from uuid import uuid4

import pytest

from tests.e2e.data import create_manage_trip_scenario, create_trip
from tests.e2e.helpers import unique_suffix
from tests.e2e.types import SessionFactory


@pytest.mark.full
def test_manage_trip_application_approve_flow_persists(session_factory: SessionFactory) -> None:
    """Host approves a pending application via the ApplicationManager embedded in
    TripDetail (/trips/:id).  The old /manage-trip/:id page was removed in Lovable;
    host management now lives on the trip detail page itself."""
    scenario = create_manage_trip_scenario(name="manage-approve")
    host = session_factory(name="manage-approve-host", username=scenario.host_username)
    page = host.page

    page.goto(f"/trips/{scenario.trip_id}")
    page.get_by_role("heading", name=scenario.title).wait_for()

    # ApplicationManager renders at the bottom of TripDetail for the host.
    # The CardTitle renders as an h3.
    page.get_by_role("heading", name="Applications").wait_for()

    # Approve the pending applicant and assert the API call succeeded.
    with page.expect_response(re.compile(r"/frontend-api/hosting-requests/\d+/decision/")) as approve_resp:
        page.get_by_role("button", name="Approve").first.click()
    assert approve_resp.value.ok, f"Approve decision failed: HTTP {approve_resp.value.status}"

    # ApplicationManager re-fetches after the decision; approved badge should appear.
    page.get_by_text("approved").first.wait_for()

    page.reload()
    page.get_by_role("heading", name="Applications").wait_for()
    page.get_by_text("approved").first.wait_for()

    host.audit.assert_clean()


@pytest.mark.full
def test_manage_trip_booking_status_toggle(session_factory: SessionFactory) -> None:
    """Host can close and reopen bookings via the Host Controls section on TripDetail.

    Previously blocked_by_lovable_showstopper — the 'Close Bookings' / 'Reopen
    Bookings' buttons were added in the latest Lovable pull.
    """
    trip_id = create_trip(
        host_username="mei",
        title=unique_suffix("Guardrail BookingStatus"),
        booking_status="open",
    )
    host = session_factory(name="manage-booking-status", username="mei")
    page = host.page

    page.goto(f"/trips/{trip_id}")
    close_btn = page.get_by_role("button", name="Close Bookings")
    close_btn.wait_for()

    with page.expect_response(re.compile(rf"/frontend-api/trips/{trip_id}/booking-status/")) as resp:
        close_btn.click()
    assert resp.value.ok, f"Close bookings failed: HTTP {resp.value.status}"
    page.get_by_role("button", name="Reopen Bookings").wait_for()

    page.reload()
    page.get_by_role("button", name="Reopen Bookings").wait_for()

    host.audit.assert_clean()


@pytest.mark.full
def test_manage_trip_cancel_trip_dialog(session_factory: SessionFactory) -> None:
    """Host can cancel a trip via the Cancel Trip AlertDialog on TripDetail.

    Previously blocked_by_lovable_showstopper — the Cancel Trip button and
    confirmation dialog were added in the latest Lovable pull.
    """
    trip_id = create_trip(
        host_username="mei",
        title=unique_suffix("Guardrail Cancel"),
    )
    host = session_factory(name="manage-cancel-trip", username="mei")
    page = host.page

    page.goto(f"/trips/{trip_id}")
    page.get_by_role("button", name="Cancel Trip").wait_for()
    page.get_by_role("button", name="Cancel Trip").click()

    alert = page.locator("[role='alertdialog']")
    alert.wait_for(state="visible")
    alert.get_by_placeholder("Why is the trip being cancelled?").fill("Guardrail cancellation test.")

    with page.expect_response(re.compile(rf"/frontend-api/trips/{trip_id}/cancel/")) as resp:
        alert.get_by_role("button", name="Cancel Trip").click()
    assert resp.value.ok, f"Trip cancel failed: HTTP {resp.value.status}"
    alert.wait_for(state="hidden")

    host.audit.assert_clean()


@pytest.mark.full
def test_manage_trip_remove_participant_flow(session_factory: SessionFactory) -> None:
    """Host can remove a confirmed participant via ApplicationManager on TripDetail.

    Previously blocked_by_lovable_showstopper — the Remove button was added in
    the latest Lovable pull.
    """
    scenario = create_manage_trip_scenario(name="manage-remove")
    host = session_factory(name="manage-remove-participant", username=scenario.host_username)
    page = host.page

    page.goto(f"/trips/{scenario.trip_id}")
    page.get_by_role("heading", name="Applications").wait_for()
    page.get_by_text(scenario.participant_display_name).wait_for()

    # The confirmed-participant row has the Remove button.
    page.get_by_role("button", name="Remove").first.click()

    confirm = page.locator("[role='alertdialog']")
    confirm.wait_for(state="visible")
    confirm.get_by_text(scenario.participant_display_name).wait_for()

    with page.expect_response(
        re.compile(rf"/frontend-api/trips/{scenario.trip_id}/participants/\d+/remove/")
    ) as resp:
        confirm.get_by_role("button", name="Remove").click()
    assert resp.value.ok, f"Participant removal failed: HTTP {resp.value.status}"

    confirm.wait_for(state="hidden")
    page.get_by_text("removed from trip.").wait_for()

    page.reload()
    page.get_by_role("heading", name="Applications").wait_for()
    page.wait_for_load_state("networkidle")

    host.audit.assert_clean()


@pytest.mark.full
def test_manage_trip_broadcast_message(session_factory: SessionFactory) -> None:
    """Host can send a broadcast message to all confirmed participants via ApplicationManager.

    Previously blocked_by_lovable_showstopper — the Message All button and dialog
    were added in the latest Lovable pull.
    """
    scenario = create_manage_trip_scenario(name="manage-broadcast")
    host = session_factory(name="manage-broadcast-host", username=scenario.host_username)
    page = host.page

    page.goto(f"/trips/{scenario.trip_id}")
    page.get_by_role("heading", name="Applications").wait_for()
    page.get_by_role("button", name="Message All").wait_for()
    page.get_by_role("button", name="Message All").click()

    dialog = page.locator("[role='dialog']").filter(has_text="Message All Participants")
    dialog.wait_for(state="visible")
    dialog.get_by_placeholder("Write your update\u2026").fill("Guardrail broadcast test message.")

    with page.expect_response(
        re.compile(rf"/frontend-api/trips/{scenario.trip_id}/broadcast/")
    ) as resp:
        dialog.get_by_role("button", name="Send").click()
    assert resp.value.ok, f"Broadcast failed: HTTP {resp.value.status}"

    dialog.wait_for(state="hidden")
    page.get_by_text("Message sent to").wait_for()

    host.audit.assert_clean()
