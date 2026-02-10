from __future__ import annotations

from typing import Final
from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import MediaAsset, remove_media_attachment, submit_media_upload

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
        print(f"[media][verbose] {message}", flush=True)


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
def media_upload_view(request: HttpRequest) -> HttpResponse:
    asset, attachment, outcome, target = submit_media_upload(
        member=request.user,
        target_type=request.POST.get("target_type"),
        target_id=request.POST.get("target_id"),
        uploaded_file=request.FILES.get("file"),
        caption=request.POST.get("caption", ""),
    )

    fallback_next = reverse("home")
    if target is not None:
        fallback_next = target.target_url or fallback_next
        if "#" not in fallback_next:
            fallback_next = f"{fallback_next}#media"

    next_url = _safe_next_url(request, fallback=fallback_next)

    if outcome == "created":
        messages.success(request, "Media uploaded.")
    elif outcome == "attached-existing":
        messages.success(request, "Existing media attached to this target.")
    elif outcome == "already-attached":
        messages.info(request, "This media file is already attached to that target.")
    elif outcome == "missing-file":
        messages.error(request, "Please choose a file to upload.")
    elif outcome == "invalid-target-type":
        messages.error(request, "Unsupported media target type.")
    elif outcome == "target-not-found":
        messages.error(request, "Could not upload media because the target was not found.")
    elif outcome == "permission-denied":
        messages.error(request, "You do not have permission to upload media for that target.")
    elif outcome == "empty-file":
        messages.error(request, "Uploaded file is empty.")
    elif outcome == "file-too-large":
        messages.error(request, "Uploaded file exceeds the allowed size limit.")
    elif outcome == "invalid-content-type":
        messages.error(request, "Only approved image/video formats can be uploaded.")
    elif outcome == "invalid-image":
        messages.error(request, "Image file validation failed. Upload a valid image file.")
    elif outcome == "too-long-caption":
        messages.error(
            request,
            f"Caption is too long. Max length is {MediaAsset.CAPTION_MAX_LENGTH} characters.",
        )
    else:
        messages.error(request, "Could not upload media. Please try again.")

    _vprint(
        request,
        (
            "Upload outcome={outcome}; member=@{member}; target={target}; attachment_id={attachment_id}; asset_id={asset_id}"
            .format(
                outcome=outcome,
                member=request.user.username,
                target=(f"{target.target_type}:{target.target_key}" if target is not None else "n/a"),
                attachment_id=(attachment.pk if attachment is not None else "n/a"),
                asset_id=(asset.pk if asset is not None else "n/a"),
            )
        ),
    )
    return redirect(next_url)


@login_required(login_url="accounts:login")
@require_POST
def media_delete_view(request: HttpRequest, attachment_id: int) -> HttpResponse:
    attachment, outcome = remove_media_attachment(
        member=request.user,
        attachment_id=attachment_id,
    )

    fallback_next = reverse("home")
    if attachment is not None:
        target_url = str(attachment.target_url or "").strip()
        if target_url:
            fallback_next = target_url if "#" in target_url else f"{target_url}#media"

    next_url = _safe_next_url(request, fallback=fallback_next)

    if outcome in {"deleted-attachment", "deleted-attachment-and-asset"}:
        messages.success(request, "Media deleted.")
    elif outcome == "permission-denied":
        messages.error(request, "You do not have permission to delete that media attachment.")
    elif outcome == "not-found":
        messages.error(request, "Media attachment not found.")
    else:
        messages.error(request, "Could not delete media attachment.")

    _vprint(
        request,
        (
            "Delete outcome={outcome}; member=@{member}; attachment_id={attachment_id}; target={target}"
            .format(
                outcome=outcome,
                member=request.user.username,
                attachment_id=attachment_id,
                target=(
                    f"{attachment.target_type}:{attachment.target_key}"
                    if attachment is not None
                    else "n/a"
                ),
            )
        ),
    )
    return redirect(next_url)
