from __future__ import annotations

import re

import pytest

from tests.e2e.helpers import fill_rich_text_editor, unique_suffix
from tests.e2e.types import SessionFactory


@pytest.mark.full
def test_create_and_edit_story(session_factory: SessionFactory) -> None:
    """Create, then edit a story through the production Stories UI.

    The old /experiences/* routes were replaced by /stories/* in Lovable.
    The story-delete UI was also removed from Lovable (no delete button exists
    on StoryDetail or StoryEdit); that flow is blocked_by_lovable_showstopper
    and tracked in the comment at the bottom of this file.
    """
    author = session_factory(name="story-crud", username="mei")
    page = author.page
    title = unique_suffix("Guardrail Story")
    updated_title = f"{title} Updated"
    description = "Created by the production-flow guardrail."
    updated_description = "Updated through the production story editor."
    body = "This story was created by the real-browser guardrail."
    updated_body = "This story was updated by the production-flow guardrail."
    location = "Guardrail Valley"

    # ── Create ────────────────────────────────────────────────────────────────
    page.goto("/stories")
    page.get_by_role("heading", name="Stories").wait_for()
    page.get_by_role("button", name="Write").click()

    page.wait_for_url(re.compile(r".*/stories/new/?$"))
    page.get_by_role("heading", name="Write a story").wait_for()
    page.get_by_placeholder("Your story title").fill(title)
    page.get_by_placeholder("A one-line teaser").fill(description)
    fill_rich_text_editor(page, body)
    page.get_by_placeholder("Bali, Indonesia").fill(location)
    page.get_by_role("button", name="Publish").click()

    page.wait_for_url(re.compile(r".*/stories/[-a-z0-9_]+/?$"))
    page.get_by_role("heading", name=title).wait_for()
    slug = page.url.rstrip("/").rsplit("/", 1)[-1]

    # ── Edit ──────────────────────────────────────────────────────────────────
    # StoryEdit is at /stories/:storyId/edit (storyId == slug)
    page.goto(f"/stories/{slug}/edit")
    page.wait_for_url(re.compile(rf".*/stories/{re.escape(slug)}/edit/?$"))
    page.get_by_role("heading", name="Edit story").wait_for()

    # StoryEdit inputs have no placeholders; use DOM order inside <main>
    title_input = page.locator("main").get_by_role("textbox").nth(0)
    excerpt_input = page.locator("main").get_by_role("textbox").nth(1)

    # Wait for the form to be populated with the original values
    page.wait_for_function(
        """
        ([expectedTitle]) => {
          const inputs = [...document.querySelectorAll("main input, main textarea")];
          return inputs[0]?.value === expectedTitle;
        }
        """,
        arg=[title],
    )

    title_input.fill(updated_title)
    excerpt_input.fill(updated_description)
    fill_rich_text_editor(page, updated_body, replace=True)
    page.get_by_role("button", name="Publish").click()

    page.wait_for_url(re.compile(rf".*/stories/{re.escape(slug)}/?$"))
    page.get_by_role("heading", name=updated_title).wait_for()
    page.get_by_text(updated_description).wait_for()

    author.audit.assert_clean()


@pytest.mark.full
def test_story_delete_removes_story(session_factory: SessionFactory) -> None:
    """Story owner can delete their story via the Trash2 button on StoryDetail.

    The Delete button was added in the latest Lovable pull — this flow was
    previously blocked_by_lovable_showstopper.
    """
    author = session_factory(name="story-delete", username="mei")
    page = author.page
    title = unique_suffix("Guardrail Delete Story")

    # Create a fresh story to delete.
    page.goto("/stories/new")
    page.get_by_role("heading", name="Write a story").wait_for()
    page.get_by_placeholder("Your story title").fill(title)
    page.get_by_placeholder("A one-line teaser").fill("Story to be deleted by the guardrail.")
    fill_rich_text_editor(page, "This story will be deleted.")
    page.get_by_role("button", name="Publish").click()

    page.wait_for_url(re.compile(r".*/stories/[-a-z0-9_]+/?$"))
    page.get_by_role("heading", name=title).wait_for()
    slug = page.url.rstrip("/").rsplit("/", 1)[-1]

    # StoryDetail shows a Delete button only to the story owner.
    # The button triggers window.confirm — accept it.
    page.once("dialog", lambda dialog: dialog.accept())

    with page.expect_response(re.compile(r"/frontend-api/blogs/[^/]+/")) as delete_resp:
        page.get_by_role("button", name="Delete").click()
    assert delete_resp.value.ok, f"Story delete failed: HTTP {delete_resp.value.status}"

    # Successful delete navigates back to /stories.
    page.wait_for_url(re.compile(r".*/stories/?$"))
    page.get_by_role("heading", name="Stories").wait_for()

    # Verify the story is gone — the detail page should render "Story not found".
    page.goto(f"/stories/{slug}")
    page.get_by_role("heading", name="Story not found").wait_for()

    author.audit.assert_clean(
        ignore_requests=["/frontend-api/home/", "/frontend-api/activity/"],
        ignore_responses=[f"/frontend-api/blogs/{slug}/"],
        ignore_console=["404 (Not Found)"],
    )
