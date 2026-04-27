from __future__ import annotations

import re

import pytest

from tests.e2e.data import ensure_bookmark_state, ensure_member, unique_username
from tests.e2e.types import SessionFactory


def _assert_logged_out(page) -> None:
    page.get_by_role("heading", name="Explore Trips").wait_for()
    page.get_by_role("button", name="Login").first.wait_for()
    payload = page.evaluate(
        """
        async () => {
          const response = await fetch("/frontend-api/session/", {
            credentials: "include",
            headers: { Accept: "application/json" },
          });
          return response.json();
        }
        """
    )
    assert payload["authenticated"] is False


@pytest.mark.full
def test_search_route_returns_guest_results_without_client_errors(session_factory: SessionFactory) -> None:
    guest = session_factory(name="search-route")
    page = guest.page

    page.goto("/search?q=Kyoto")
    page.get_by_role("heading", name="Search").wait_for()
    assert page.get_by_placeholder("Search trips, stories, people…").input_value() == "Kyoto"
    page.get_by_text("Kyoto food lanes weekend").wait_for()

    guest.audit.assert_clean()


@pytest.mark.full
def test_bookmarks_route_renders_saved_trip_for_member(session_factory: SessionFactory) -> None:
    ensure_bookmark_state(username="sahar", trip_id=102, bookmarked=True)
    member = session_factory(name="bookmarks-route", username="sahar")
    page = member.page

    page.goto("/bookmarks")
    page.get_by_role("heading", name="Saved Trips").wait_for()
    page.get_by_text("Patagonia first-light trekking camp").wait_for()

    member.audit.assert_clean()


@pytest.mark.full
def test_dashboard_routes_render_for_authenticated_member(session_factory: SessionFactory) -> None:
    member = session_factory(name="dashboard-routes", username="mei")
    page = member.page

    page.goto("/dashboard")
    page.wait_for_url(re.compile(r".*/dashboard/trips/?$"))
    page.get_by_role("heading", name="Your trips").wait_for()
    page.get_by_role("tab", name=re.compile(r"^Joined")).wait_for()
    page.get_by_role("tab", name=re.compile(r"^Managed")).wait_for()

    page.goto("/dashboard/stories")
    page.get_by_role("heading", name="Your stories").wait_for()
    page.get_by_role("tab", name=re.compile(r"^Published")).wait_for()
    page.get_by_role("link", name=re.compile(r"New story", re.I)).wait_for()

    page.goto("/dashboard/reviews")
    page.get_by_role("heading", name="Reviews").wait_for()
    page.get_by_role("tab", name=re.compile(r"^Received")).wait_for()
    page.get_by_role("tab", name=re.compile(r"^Written")).wait_for()

    page.goto("/dashboard/subscriptions")
    page.get_by_role("heading", name="Subscriptions").wait_for()
    page.get_by_role("tab", name=re.compile(r"^Subscribers")).wait_for()
    page.get_by_role("tab", name=re.compile(r"^Subscribed")).wait_for()

    member.audit.assert_clean()


@pytest.mark.full
def test_notifications_route_renders_for_member(session_factory: SessionFactory) -> None:
    member = session_factory(name="notifications-route", username="mei")
    page = member.page

    page.goto("/notifications")
    page.get_by_role("heading", name="Notifications").wait_for()
    page.wait_for_function(
        """
        () => {
          const main = document.querySelector("main");
          return Boolean(main && main.innerText.trim().length > 40);
        }
        """
    )

    member.audit.assert_clean()


@pytest.mark.full
def test_owner_profile_edit_dialog_persists_and_preview_route_renders(session_factory: SessionFactory) -> None:
    username = unique_username("profile-surface")
    ensure_member(username=username, display_name="Profile Surface")
    member = session_factory(name="profile-edit-surface", username=username)
    page = member.page
    updated_name = "Profile Surface Updated"
    updated_location = "Guardrail City"
    updated_bio = "Updated through the production profile surface guardrail."

    page.goto(f"/users/{username}")
    page.get_by_role("heading", name="Profile Surface").wait_for()
    page.get_by_role("button", name="Edit Profile").click()

    dialog = page.locator("[role='dialog']").filter(has_text="Edit Profile")
    dialog.wait_for()
    textboxes = dialog.get_by_role("textbox")
    textboxes.nth(0).fill(updated_name)
    textboxes.nth(1).fill(updated_location)
    textboxes.nth(2).fill(updated_bio)
    with page.expect_response(re.compile(r"/frontend-api/profile/me/")) as save_response:
        dialog.get_by_role("button", name="Save Changes").click()
    assert save_response.value.ok
    dialog.wait_for(state="hidden")

    page.get_by_role("heading", name=updated_name).wait_for()
    page.get_by_text(updated_location).wait_for()
    page.get_by_text(updated_bio).wait_for()

    page.reload()
    page.get_by_role("heading", name=updated_name).wait_for()

    page.goto("/profile/edit?mode=preview")
    page.get_by_text("Private preview").wait_for()
    page.get_by_role("heading", name=updated_name).wait_for()
    page.get_by_text(updated_location).wait_for()

    member.audit.assert_clean()


@pytest.mark.full
def test_settings_deactivate_account_logs_member_out(session_factory: SessionFactory) -> None:
    username = unique_username("settings-deactivate")
    ensure_member(username=username, display_name="Deactivate User")
    member = session_factory(name="settings-deactivate", username=username)
    page = member.page

    page.goto("/settings")
    page.get_by_role("heading", name="Settings").wait_for()
    page.get_by_role("button", name="Deactivate account").click()

    dialog = page.locator("[role='alertdialog']")
    dialog.wait_for()
    dialog.get_by_role("button", name="Deactivate").click()

    _assert_logged_out(page)
    member.audit.assert_clean()


@pytest.mark.full
def test_settings_delete_account_logs_member_out(session_factory: SessionFactory) -> None:
    username = unique_username("settings-delete")
    ensure_member(username=username, display_name="Delete User")
    member = session_factory(name="settings-delete", username=username)
    page = member.page

    page.goto("/settings")
    page.get_by_role("heading", name="Settings").wait_for()
    page.get_by_role("button", name="Delete permanently").click()

    dialog = page.locator("[role='alertdialog']")
    dialog.wait_for()
    dialog.get_by_role("button", name="Delete permanently").click()

    _assert_logged_out(page)
    member.audit.assert_clean()
