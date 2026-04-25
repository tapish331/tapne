from __future__ import annotations

import re

import pytest

from tests.e2e.data import ensure_bookmark_state, ensure_follow_state
from tests.e2e.types import SessionFactory


@pytest.mark.full
def test_follow_unfollow_persists_after_reload(session_factory: SessionFactory) -> None:
    ensure_follow_state(follower_username="sahar", following_username="arun", is_following=False)
    member = session_factory(name="profile-follow-toggle", username="sahar")
    page = member.page

    page.goto("/users/arun")
    page.get_by_role("heading", name="Arun N.").wait_for()
    with page.expect_response(re.compile(r"/frontend-api/profile/arun/follow/")) as follow_response:
        page.get_by_role("button", name="Follow").click()
    assert follow_response.value.ok
    page.get_by_role("button", name="Following").wait_for()
    page.wait_for_load_state("networkidle")

    page.reload()
    page.get_by_role("button", name="Following").wait_for()

    with page.expect_response(re.compile(r"/frontend-api/profile/arun/follow/")) as unfollow_response:
        page.get_by_role("button", name="Following").click()
    assert unfollow_response.value.ok
    page.wait_for_load_state("networkidle")
    page.reload()
    page.get_by_role("button", name="Follow").wait_for()

    member.audit.assert_clean()


@pytest.mark.full
def test_bookmark_toggle_persists_after_reload(session_factory: SessionFactory) -> None:
    ensure_bookmark_state(username="sahar", trip_id=102, bookmarked=False)
    member = session_factory(name="bookmark-toggle", username="sahar")
    page = member.page

    page.goto("/trips/102")
    title = "Patagonia first-light trekking camp"
    page.get_by_role("heading", name=title).wait_for()
    hero_actions = page.get_by_role("heading", name=title).locator("xpath=..")
    with page.expect_response(re.compile(r"/frontend-api/bookmarks/102/")) as add_bookmark_response:
        hero_actions.get_by_role("button", name="Bookmark trip").click()
    assert add_bookmark_response.value.ok
    hero_actions.get_by_role("button", name="Remove bookmark").wait_for()
    page.wait_for_load_state("networkidle")

    page.reload()
    hero_actions = page.get_by_role("heading", name=title).locator("xpath=..")
    hero_actions.get_by_role("button", name="Remove bookmark").wait_for()

    with page.expect_response(re.compile(r"/frontend-api/bookmarks/102/")) as remove_bookmark_response:
        hero_actions.get_by_role("button", name="Remove bookmark").click()
    assert remove_bookmark_response.value.ok
    page.wait_for_load_state("networkidle")
    page.reload()
    page.get_by_role("heading", name=title).locator("xpath=..").get_by_role("button", name="Bookmark trip").wait_for()

    member.audit.assert_clean()
