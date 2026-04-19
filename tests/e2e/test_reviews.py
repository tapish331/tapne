from __future__ import annotations

import re

import pytest

from tests.e2e.types import SessionFactory


@pytest.mark.full
def test_trip_review_submit_succeeds(session_factory: SessionFactory) -> None:
    """Submit a trip review through the ReviewModal on the trip detail page.

    Covers the new flow introduced in frontend_spa/src/components/ReviewModal.tsx
    and frontend_spa/src/pages/TripDetail.tsx: a "Write a Review" button opens a
    multi-step modal that POSTs to /frontend-api/trips/{id}/reviews/.

    The backend is idempotent (creates or updates), so re-runs are safe.
    """
    reviewer = session_factory(name="trip-review-submit", username="sahar")
    page = reviewer.page
    loved_text = "The organization was excellent and the people were truly amazing!"

    page.goto("/trips/101")
    page.get_by_role("heading", name="Kyoto food lanes weekend").wait_for()

    # Two "Write a Review" buttons exist (reviews section + sidebar).
    # The first is in the page body reviews section.
    page.get_by_role("button", name="Write a Review").first.click()

    dialog = page.locator("[role='dialog']")
    dialog.wait_for(state="visible")

    # ── Step 0: Select rating ──────────────────────────────────────────────
    # Five star buttons rendered in a flex row; click the 4th (rating = 4).
    dialog.locator(".flex.justify-center.gap-2 button").nth(3).click()
    # "Continue" is disabled until rating > 0; enabled after the click above.
    dialog.get_by_role("button", name="Continue").click()

    # ── Step 1: Written feedback ───────────────────────────────────────────
    # "What did you love the most?" textarea requires ≥ 10 characters.
    dialog.get_by_placeholder("The people, the places, the vibe...").fill(loved_text)
    dialog.get_by_role("button", name="Continue").click()

    # ── Step 2: Tags (optional) ────────────────────────────────────────────
    dialog.get_by_role("button", name="Continue").click()

    # ── Step 3: Photos + summary + submit ─────────────────────────────────
    with page.expect_response(re.compile(r"/frontend-api/trips/\d+/reviews/")) as review_response:
        dialog.get_by_role("button", name="Post Review").click()

    assert review_response.value.ok, (
        f"Review submit failed: HTTP {review_response.value.status}"
    )

    # Modal must close after a successful submission.
    dialog.wait_for(state="hidden")

    reviewer.audit.assert_clean()
