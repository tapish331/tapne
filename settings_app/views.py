from __future__ import annotations

from typing import Final
from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from .forms import MemberSettingsForm
from .models import (
    build_settings_payload_for_member,
    ensure_member_settings,
    resolve_member_settings_defaults,
    update_member_settings,
)

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
        print(f"[settings][verbose] {message}", flush=True)


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
@require_http_methods(["GET", "POST"])
def settings_index_view(request: HttpRequest) -> HttpResponse:
    settings_row, created = ensure_member_settings(request.user)
    if settings_row is None:
        messages.error(request, "Could not load settings for this account.")
        _vprint(request, "Settings page could not resolve member row")
        return redirect(reverse("home"))

    fallback_next = reverse("settings_app:index")

    if request.method == "POST":
        next_url = _safe_next_url(request, fallback=fallback_next)
        form = MemberSettingsForm(request.POST, instance=settings_row)
        if form.is_valid():
            updated_row, outcome = update_member_settings(
                member=request.user,
                email_updates=form.cleaned_data["email_updates"],
                profile_visibility=form.cleaned_data["profile_visibility"],
                dm_privacy=form.cleaned_data["dm_privacy"],
                search_visibility=form.cleaned_data["search_visibility"],
                digest_enabled=form.cleaned_data["digest_enabled"],
            )
            changed_fields = list(form.changed_data)

            if updated_row is None:
                messages.error(request, "Could not save settings. Please try again.")
                _vprint(request, "Settings save failed because member row could not be resolved")
                return redirect(next_url)

            if outcome in {"created", "updated"}:
                messages.success(request, "Settings saved.")
            else:
                messages.info(request, "No settings changes were detected.")

            _vprint(
                request,
                (
                    "Settings saved for @{username}; outcome={outcome}; changed_fields={changed_fields}; "
                    "email_updates={email_updates}; visibility={visibility}; dm_privacy={dm_privacy}; "
                    "search_visibility={search_visibility}; digest_enabled={digest_enabled}"
                ).format(
                    username=request.user.username,
                    outcome=outcome,
                    changed_fields=changed_fields,
                    email_updates=updated_row.email_updates,
                    visibility=updated_row.profile_visibility,
                    dm_privacy=updated_row.dm_privacy,
                    search_visibility=updated_row.search_visibility,
                    digest_enabled=updated_row.digest_enabled,
                ),
            )
            return redirect(next_url)

        messages.error(request, "Please fix the highlighted fields.")
        _vprint(
            request,
            (
                "Settings validation failed for @{username}; errors={errors}"
            ).format(
                username=request.user.username,
                errors=form.errors.get_json_data(),
            ),
        )
    else:
        form = MemberSettingsForm(instance=settings_row)
        _vprint(
            request,
            (
                "Rendered settings page for @{username}; created={created}; "
                "email_updates={email_updates}; visibility={visibility}; dm_privacy={dm_privacy}; "
                "search_visibility={search_visibility}; digest_enabled={digest_enabled}"
            ).format(
                username=request.user.username,
                created=created,
                email_updates=settings_row.email_updates,
                visibility=settings_row.profile_visibility,
                dm_privacy=settings_row.dm_privacy,
                search_visibility=settings_row.search_visibility,
                digest_enabled=settings_row.digest_enabled,
            ),
        )

    payload = build_settings_payload_for_member(request.user)
    if created and payload["settings"] is not None:
        payload["reason"] = "Settings were initialized using environment-driven defaults for this member."

    context: dict[str, object] = {
        "settings_form": form,
        "settings_record": payload["settings"],
        "settings_mode": payload["mode"],
        "settings_reason": payload["reason"],
        "settings_defaults": resolve_member_settings_defaults(),
    }
    return render(request, "pages/settings/index.html", context)
