from __future__ import annotations

import re

import pytest

from tests.e2e.helpers import unique_suffix
from tests.e2e.types import SessionFactory


def _visible_message(page, text: str):
    return page.locator("p.whitespace-pre-wrap:visible").filter(has_text=text).last


@pytest.mark.full
def test_trip_detail_dm_start_creates_thread_visible_to_both_users(session_factory: SessionFactory) -> None:
    traveler = session_factory(name="trip-detail-dm-traveler", username="arun")
    host = session_factory(name="trip-detail-dm-host", username="mei")
    message = unique_suffix("trip-detail-dm")

    traveler.page.goto("/trips/101")
    traveler.page.get_by_role("heading", name="Kyoto food lanes weekend").wait_for()
    traveler.page.get_by_role("button", name="Ask a Question").click()
    traveler.page.wait_for_url(re.compile(r".*/messages\?thread=\d+"))
    traveler.page.get_by_role("heading", name="Inbox").wait_for()
    composer = traveler.page.locator("input[placeholder='Type a message...']:visible")
    composer.fill(message)
    # Wait for the message POST to complete before navigating as the host.
    with traveler.page.expect_response(re.compile(r"/frontend-api/dm/inbox/\d+/messages/")) as send_resp:
        composer.press("Enter")
    assert send_resp.value.ok, f"Message send failed: {send_resp.value.status}"
    _visible_message(traveler.page, message).wait_for()

    host.page.goto("/messages?dm=arun")
    host.page.get_by_role("heading", name="Inbox").wait_for()
    host.page.get_by_role("button", name=re.compile(r"Arun N\.", re.I)).first.click()
    _visible_message(host.page, message).wait_for()

    traveler.audit.assert_clean()
    host.audit.assert_clean()
