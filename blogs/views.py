from __future__ import annotations

from typing import Final

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from interactions.models import build_comment_threads_payload_for_target
from media.models import (
    MediaTargetPayload,
    build_media_attachment_map_for_targets,
    build_media_payload_for_target,
)
from reviews.models import build_reviews_payload_for_target

from .forms import BlogForm
from .models import Blog, build_blog_detail_payload_for_user, build_blog_list_payload_for_user

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
        print(f"[blogs][verbose] {message}", flush=True)


@require_http_methods(["GET"])
def blog_list_view(request: HttpRequest) -> HttpResponse:
    viewer_state = "member" if request.user.is_authenticated else "guest"
    _vprint(request, f"Rendering blog list for viewer_state={viewer_state}")

    payload = build_blog_list_payload_for_user(request.user)
    _vprint(
        request,
        (
            "Blog list mode={mode}; source={source}; reason={reason}; count={count}".format(
                mode=payload["mode"],
                source=payload["source"],
                reason=payload["reason"],
                count=len(payload["blogs"]),
            )
        ),
    )

    context: dict[str, object] = {
        "blogs": payload["blogs"],
        "blog_mode": payload["mode"],
        "blog_reason": payload["reason"],
        "blog_source": payload["source"],
    }
    return render(request, "pages/blogs/list.html", context)


@require_http_methods(["GET"])
def blog_detail_view(request: HttpRequest, slug: str) -> HttpResponse:
    payload = build_blog_detail_payload_for_user(request.user, slug)
    comments_payload = build_comment_threads_payload_for_target(
        target_type="blog",
        target_id=slug,
    )
    reviews_payload = build_reviews_payload_for_target(
        target_type="blog",
        target_id=slug,
        viewer=request.user,
    )
    review_items = [dict(item) for item in reviews_payload["reviews"]]
    review_key_map = build_media_attachment_map_for_targets(
        target_type="review",
        target_ids=[item.get("id") for item in review_items],
        viewer=request.user,
        limit_per_target=4,
    )
    for review_item in review_items:
        review_item["media_attachments"] = review_key_map.get(str(review_item.get("id") or ""), [])

    blog_media_payload: MediaTargetPayload
    if payload["source"] == "live-db":
        blog_media_payload = build_media_payload_for_target(
            target_type="blog",
            target_id=slug,
            viewer=request.user,
        )
    else:
        blog_media_payload = {
            "attachments": [],
            "mode": "unavailable-target",
            "reason": "No media yet for this preview post. Authors can add photos and clips once the post is published live.",
            "target_type": "blog",
            "target_key": str(slug),
            "target_label": str(payload["blog"].get("title", slug.replace("-", " ").title())),
            "target_url": str(payload["blog"].get("url", f"/blogs/{slug}/")),
            "can_upload": False,
        }
    _vprint(
        request,
        (
            "Blog detail slug={slug}; mode={mode}; source={source}; can_manage={can_manage}".format(
                slug=slug,
                mode=payload["mode"],
                source=payload["source"],
                can_manage=payload["can_manage_blog"],
            )
        ),
    )
    _vprint(
        request,
        (
            "Blog comments target={target}; mode={mode}; count={count}".format(
                target=f"{comments_payload['target_type']}:{comments_payload['target_key']}",
                mode=comments_payload["mode"],
                count=len(comments_payload["comments"]),
            )
        ),
    )
    _vprint(
        request,
        (
            "Blog reviews target={target}; mode={mode}; count={count}; average={average}".format(
                target=f"{reviews_payload['target_type']}:{reviews_payload['target_key']}",
                mode=reviews_payload["mode"],
                count=reviews_payload["review_count"],
                average=reviews_payload["average_rating"],
            )
        ),
    )
    _vprint(
        request,
        (
            "Blog media target={target}; mode={mode}; count={count}; can_upload={can_upload}".format(
                target=f"{blog_media_payload['target_type']}:{blog_media_payload['target_key']}",
                mode=blog_media_payload["mode"],
                count=len(blog_media_payload["attachments"]),
                can_upload=blog_media_payload["can_upload"],
            )
        ),
    )

    context: dict[str, object] = {
        "blog": payload["blog"],
        "blog_detail_mode": payload["mode"],
        "blog_detail_reason": payload["reason"],
        "blog_detail_source": payload["source"],
        "can_manage_blog": payload["can_manage_blog"],
        "interaction_comments": comments_payload["comments"],
        "interaction_comment_mode": comments_payload["mode"],
        "interaction_comment_reason": comments_payload["reason"],
        "review_items": review_items,
        "review_rating_buckets": reviews_payload["rating_buckets"],
        "review_mode": reviews_payload["mode"],
        "review_reason": reviews_payload["reason"],
        "review_count": reviews_payload["review_count"],
        "review_average_rating": reviews_payload["average_rating"],
        "review_can_review": reviews_payload["can_review"],
        "review_viewer_row": reviews_payload["viewer_review"],
        "blog_media_items": blog_media_payload["attachments"],
        "blog_media_mode": blog_media_payload["mode"],
        "blog_media_reason": blog_media_payload["reason"],
        "blog_media_can_upload": blog_media_payload["can_upload"],
    }
    return render(request, "pages/blogs/detail.html", context)


@login_required(login_url="accounts:login")
@require_http_methods(["GET", "POST"])
def blog_create_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = BlogForm(request.POST)
        if form.is_valid():
            blog = form.save(commit=False)
            blog.author = request.user
            blog.save()

            messages.success(request, "Blog created.")
            _vprint(request, f"Created blog slug={blog.slug} for @{request.user.username}")
            return redirect(reverse("blogs:detail", kwargs={"slug": blog.slug}))

        messages.error(request, "Please fix the highlighted fields.")
        _vprint(request, "Blog create failed due to form validation errors")
    else:
        form = BlogForm(initial={"is_published": True})
        _vprint(request, f"Rendered blog create form for @{request.user.username}")

    context: dict[str, object] = {
        "form": form,
        "form_mode": "create",
        "page_title": "Create blog",
        "submit_label": "Create blog",
    }
    return render(request, "pages/blogs/form.html", context)


@login_required(login_url="accounts:login")
@require_http_methods(["GET", "POST"])
def blog_edit_view(request: HttpRequest, slug: str) -> HttpResponse:
    blog = get_object_or_404(Blog, slug=slug, author=request.user)

    if request.method == "POST":
        form = BlogForm(request.POST, instance=blog)
        if form.is_valid():
            updated_blog = form.save()
            messages.success(request, "Blog updated.")
            _vprint(request, f"Updated blog slug={updated_blog.slug} for @{request.user.username}")
            return redirect(reverse("blogs:detail", kwargs={"slug": updated_blog.slug}))

        messages.error(request, "Please fix the highlighted fields.")
        _vprint(request, f"Blog edit failed for slug={slug} due to form validation errors")
    else:
        form = BlogForm(instance=blog)
        _vprint(request, f"Rendered blog edit form for slug={slug} and @{request.user.username}")

    context: dict[str, object] = {
        "form": form,
        "form_mode": "edit",
        "blog": blog,
        "page_title": "Edit blog",
        "submit_label": "Save changes",
    }
    return render(request, "pages/blogs/form.html", context)


@login_required(login_url="accounts:login")
@require_POST
def blog_delete_view(request: HttpRequest, slug: str) -> HttpResponse:
    blog = get_object_or_404(Blog, slug=slug, author=request.user)
    blog_title = blog.title
    blog.delete()

    messages.success(request, f"Deleted blog: {blog_title}")
    _vprint(request, f"Deleted blog slug={slug} for @{request.user.username}")
    return redirect(reverse("blogs:list"))
