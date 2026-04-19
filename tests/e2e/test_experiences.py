from __future__ import annotations

import re

import pytest

from tests.e2e.helpers import fill_rich_text_editor, unique_suffix
from tests.e2e.types import SessionFactory


@pytest.mark.full
def test_create_edit_and_delete_experience(session_factory: SessionFactory) -> None:
    author = session_factory(name="experience-crud", username="mei")
    page = author.page
    title = unique_suffix("Guardrail Experience")
    updated_title = f"{title} Updated"
    description = "Created by the production-flow guardrail."
    updated_excerpt = "Updated through the production blog editor."
    updated_body = "This experience was updated by the production-flow guardrail."

    page.goto("/experiences")
    page.get_by_role("heading", name="Travel Experiences").wait_for()
    page.get_by_role("button", name="Write").click()

    page.wait_for_url(re.compile(r".*/experiences/create/?$"))
    page.get_by_role("heading", name="Share Your Experience").wait_for()
    page.get_by_placeholder("Give your experience a title").fill(title)
    page.get_by_placeholder("A brief summary for the card preview").fill(description)
    fill_rich_text_editor(page, "This experience was created by the real-browser guardrail.")
    page.get_by_placeholder("e.g., Manali, Himachal Pradesh").fill("Guardrail Valley")
    page.get_by_role("button", name="Publish Experience").click()

    page.wait_for_url(re.compile(r".*/experiences/?$"))
    page.get_by_role("link", name=re.compile(title)).click()
    page.wait_for_url(re.compile(r".*/experiences/[-a-z0-9_]+/?$"))
    page.get_by_role("heading", name=title).wait_for()
    slug = page.url.rstrip("/").rsplit("/", 1)[-1]

    page.goto(f"/experiences/edit?slug={slug}")
    page.wait_for_url(re.compile(rf".*/experiences/edit\?slug={re.escape(slug)}$"))
    title_input = page.get_by_placeholder("Give your experience a title")
    excerpt_input = page.get_by_placeholder("A brief summary for the card preview")
    title_input.wait_for()
    excerpt_input.wait_for()
    page.wait_for_function(
        """
        ([expectedTitle, expectedExcerpt]) => {
          const titleInput = document.querySelector("input[placeholder='Give your experience a title']");
          const excerptInput = document.querySelector("input[placeholder='A brief summary for the card preview']");
          return titleInput?.value === expectedTitle && excerptInput?.value === expectedExcerpt;
        }
        """,
        arg=[title, description],
    )
    title_input.fill(updated_title)
    excerpt_input.fill(updated_excerpt)
    fill_rich_text_editor(page, updated_body, replace=True)
    page.get_by_role("button", name="Update Experience").click()

    page.wait_for_url(re.compile(rf".*/experiences/{re.escape(slug)}/?$"))
    page.get_by_role("heading", name=updated_title).wait_for()
    page.get_by_text(updated_excerpt).wait_for()

    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name=re.compile("^Delete")).click()
    page.wait_for_url(re.compile(r".*/experiences/?$"))
    assert page.get_by_text(updated_title).count() == 0

    author.audit.assert_clean()
