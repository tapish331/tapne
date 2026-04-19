from __future__ import annotations

import re

import pytest

from tests.e2e.types import SessionFactory


@pytest.mark.smoke
def test_home_and_trip_catalog_render_without_client_errors(session_factory: SessionFactory) -> None:
    guest = session_factory(name="guest-home-catalog")
    page = guest.page

    page.goto("/")
    page.get_by_role("heading", name="Explore Trips").wait_for()

    page.goto("/trips")
    page.get_by_role("heading", name="Explore Trips").wait_for()
    page.get_by_role("heading", name="Kyoto food lanes weekend").wait_for()

    guest.audit.assert_clean()


@pytest.mark.smoke
def test_trip_detail_renders_live_trip_data(session_factory: SessionFactory) -> None:
    guest = session_factory(name="guest-trip-detail")
    page = guest.page

    page.goto("/trips/101")
    page.get_by_role("heading", name="Kyoto food lanes weekend").wait_for()
    page.get_by_role("button", name=re.compile("Join Waitlist|Book Now")).first.wait_for()

    guest.audit.assert_clean()
