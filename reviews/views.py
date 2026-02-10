from __future__ import annotations

from typing import Final
from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from media.models import build_media_attachment_map_for_targets, build_media_payload_for_target

from .models import Review, build_reviews_payload_for_target, submit_review

VERBOSE_FLAGS: Final[set[str]] = {"1", "true", "yes", "on"}


def _is_verbose_request(request: HttpRequest) -> bool:
    candidate = (
        request.GET.get("verbose")
        or request.POST.get("verbose")
        or request.headers.get("X-Tapne-Verbose")
        or ""
    )
    return candidate.strip().lower() in VERBOSE_FLAGS


def _vprint(request: HttpRequest, message: str) -> None:
    if _is_verbose_request(request):
        print(f"[reviews][verbose] {message}", flush=True)


def _safe_next_url(request: HttpRequest, fallback: str) -> str:
    """
    Resolve post-action redirect target while preventing open redirects.
    """

    allowed_hosts = {request.get_host()}
    require_https = request.is_secure()

    requested_next = str(request.POST.get("next") or request.GET.get("next") or "").strip()
    if requested_next and url_has_allowed_host_and_scheme(
        requested_next,
        allowed_hosts=allowed_hosts,
        require_https=require_https,
    ):
        return requested_next

    referer = str(request.headers.get("Referer", "") or "").strip()
    if referer and url_has_allowed_host_and_scheme(
        referer,
        allowed_hosts=allowed_hosts,
        require_https=require_https,
    ):
        split = urlsplit(referer)
        query = f"?{split.query}" if split.query else ""
        fragment = f"#{split.fragment}" if split.fragment else ""
        return f"{split.path or '/'}{query}{fragment}"

    return fallback


@login_required(login_url="accounts:login")
@require_POST
def review_create_view(request: HttpRequest) -> HttpResponse:
    review_row, outcome, target = submit_review(
        member=request.user,
        target_type=request.POST.get("target_type"),
        target_id=request.POST.get("target_id"),
        rating=request.POST.get("rating"),
        headline=request.POST.get("headline", ""),
        body=request.POST.get("body", ""),
    )

    fallback_next = reverse("home")
    if target is not None:
        fallback_next = target.target_url
        if "#" not in fallback_next:
            fallback_next = f"{fallback_next}#reviews"
    next_url = _safe_next_url(request, fallback=fallback_next)

    if outcome == "created":
        messages.success(request, "Review posted.")
    elif outcome == "updated":
        messages.success(request, "Review updated.")
    elif outcome == "invalid-target-type":
        messages.error(request, "Unsupported review target type. Use trip or blog.")
    elif outcome == "target-not-found":
        messages.error(request, "Could not save review because that target was not found.")
    elif outcome == "invalid-rating":
        messages.error(
            request,
            f"Rating must be between {Review.RATING_MIN} and {Review.RATING_MAX}.",
        )
    elif outcome == "empty-body":
        messages.info(request, "Review text cannot be empty.")
    elif outcome == "too-long-headline":
        messages.error(request, f"Headline is too long. Max length is {Review.HEADLINE_MAX_LENGTH} characters.")
    elif outcome == "too-long-body":
        messages.error(request, f"Review is too long. Max length is {Review.BODY_MAX_LENGTH} characters.")
    else:
        messages.error(request, "Could not save review. Please try again.")

    _vprint(
        request,
        (
            "Review outcome={outcome}; member=@{member}; target={target}; review_id={review_id}".format(
                outcome=outcome,
                member=request.user.username,
                target=(f"{target.target_type}:{target.target_key}" if target is not None else "n/a"),
                review_id=(review_row.pk if review_row is not None else "n/a"),
            )
        ),
    )
    return redirect(next_url)


@require_http_methods(["GET"])
def review_target_list_view(request: HttpRequest, target_type: str, target_id: str) -> HttpResponse:
    payload = build_reviews_payload_for_target(
        target_type=target_type,
        target_id=target_id,
        viewer=request.user,
    )
    review_items = [dict(item) for item in payload["reviews"]]
    review_key_map = build_media_attachment_map_for_targets(
        target_type="review",
        target_ids=[item.get("id") for item in review_items],
        viewer=request.user,
        limit_per_target=4,
    )
    for review_item in review_items:
        review_item["media_attachments"] = review_key_map.get(str(review_item.get("id") or ""), [])

    target_media_payload = build_media_payload_for_target(
        target_type=payload["target_type"],
        target_id=payload["target_key"],
        viewer=request.user,
    )
    _vprint(
        request,
        (
            "Review list target={target}; mode={mode}; count={count}; average={average}".format(
                target=f"{payload['target_type']}:{payload['target_key']}",
                mode=payload["mode"],
                count=payload["review_count"],
                average=payload["average_rating"],
            )
        ),
    )
    _vprint(
        request,
        (
            "Target media mode={mode}; count={count}; can_upload={can_upload}".format(
                mode=target_media_payload["mode"],
                count=len(target_media_payload["attachments"]),
                can_upload=target_media_payload["can_upload"],
            )
        ),
    )

    context: dict[str, object] = {
        "review_items": review_items,
        "review_rating_buckets": payload["rating_buckets"],
        "review_mode": payload["mode"],
        "review_reason": payload["reason"],
        "review_target_type": payload["target_type"],
        "review_target_key": payload["target_key"],
        "review_target_label": payload["target_label"],
        "review_target_url": payload["target_url"],
        "review_count": payload["review_count"],
        "review_average_rating": payload["average_rating"],
        "review_can_review": payload["can_review"],
        "review_viewer_row": payload["viewer_review"],
        "target_media_items": target_media_payload["attachments"],
        "target_media_mode": target_media_payload["mode"],
        "target_media_reason": target_media_payload["reason"],
        "target_media_can_upload": target_media_payload["can_upload"],
    }
    return render(request, "pages/reviews/list.html", context)
