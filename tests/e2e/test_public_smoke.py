from __future__ import annotations

import re

import pytest

from tests.e2e.data import create_trip, ensure_member
from tests.e2e.helpers import unique_suffix
from tests.e2e.types import SessionFactory


@pytest.mark.smoke
def test_home_and_trip_catalog_render_without_client_errors(session_factory: SessionFactory) -> None:
    host_username = ensure_member(username="smoke-public-host", display_name="Smoke Public Host")
    trip_id = create_trip(host_username=host_username, title=unique_suffix("Smoke public catalog trip"))

    guest = session_factory(name="guest-home-catalog")
    page = guest.page

    page.goto("/")
    page.get_by_role("heading", name="Explore Trips").wait_for()

    page.goto("/search")
    page.get_by_role("heading", name="Search").wait_for()
    page.locator(f"a[href='/trips/{trip_id}']").first.wait_for()

    guest.audit.assert_clean()


@pytest.mark.smoke
def test_trip_detail_renders_live_trip_data(session_factory: SessionFactory) -> None:
    host_username = ensure_member(username="smoke-detail-host", display_name="Smoke Detail Host")
    title = unique_suffix("Smoke detail live trip")
    trip_id = create_trip(host_username=host_username, title=title)

    guest = session_factory(name="guest-trip-detail")
    page = guest.page

    page.goto(f"/trips/{trip_id}")
    page.locator("h1").filter(has_text=title).wait_for()
    page.get_by_role("button", name=re.compile("Join Waitlist|Book Now")).first.wait_for()

    guest.audit.assert_clean()
