from __future__ import annotations

import re

import pytest

from tests.e2e.helpers import fill_trip_basics, future_trip_window, unique_suffix
from tests.e2e.types import SessionFactory


@pytest.mark.smoke
def test_create_save_and_publish_trip_persists_across_reload(session_factory: SessionFactory) -> None:
    host = session_factory(name="draft-create-publish", username="mei")
    page = host.page
    title = unique_suffix("Guardrail Trip")
    summary = "A deterministic smoke-suite trip created through the production form."
    start_date, end_date, close_date = future_trip_window()

    page.goto("/create-trip")
    page.get_by_role("heading", name="Create a Trip").wait_for()
    fill_trip_basics(
        page,
        title=title,
        summary=summary,
        destination="Guardrail Valley",
        starts_at=start_date,
        ends_at=end_date,
        booking_closes_at=close_date,
    )

    page.get_by_role("button", name="Save Draft").last.click()
    page.get_by_role("button", name="Saved!").first.wait_for()

    page.goto("/my-trips")
    page.get_by_role("heading", name="My Trips").wait_for()
    page.get_by_text(title).wait_for()

    page.reload()
    page.get_by_text(title).wait_for()

    draft_card = page.locator("div").filter(has_text=title).filter(has_text="Edit Draft").first
    draft_card.get_by_role("button", name="Edit Draft").first.click()
    page.get_by_role("heading", name="Create a Trip").wait_for()
    assert page.locator("input[placeholder='e.g. Spiti Valley Road Trip']").input_value() == title
    assert page.locator("textarea[placeholder*='A thrilling road trip']").input_value() == summary

    page.get_by_role("button", name="Publish Trip").click()
    page.wait_for_url(re.compile(r".*/my-trips/?$"))
    page.get_by_role("heading", name="My Trips").wait_for()

    page.get_by_role("tab", name=re.compile("^Published")).click()
    page.get_by_text(title).wait_for()

    page.reload()
    page.get_by_role("tab", name=re.compile("^Published")).click()
    page.get_by_text(title).wait_for()

    host.audit.assert_clean()
