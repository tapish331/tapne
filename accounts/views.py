from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from typing import Any, Final, Protocol, TypedDict, cast

from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from .forms import LoginForm, ProfileEditForm, SignUpForm
from .models import AccountProfile, ensure_profile
from social.models import build_follow_stats_for_user, is_following_user

UserModel = get_user_model()


VERBOSE_FLAGS: Final[set[str]] = {"1", "true", "yes", "on"}
AUTH_MODAL_QUERY_KEYS: Final[set[str]] = {"auth", "auth_reason", "auth_error", "auth_next"}
AUTH_MODAL_FEEDBACK_SESSION_KEY: Final[str] = "auth_modal_feedback"


class ProfileUserLike(Protocol):
    username: str
    email: str
    date_joined: datetime

    def get_username(self) -> str: ...


class ProfilePayload(TypedDict):
    username: str
    display_name: str
    bio: str
    location: str
    website: str
    email: str
    joined_at: datetime | None


@dataclass(frozen=True)
class DemoPublicProfile:
    username: str
    display_name: str
    bio: str
    location: str
    website: str = ""


DEMO_PUBLIC_PROFILES: Final[dict[str, DemoPublicProfile]] = {
    "mei": DemoPublicProfile(
        username="mei",
        display_name="Mei Tanaka",
        bio="Street-food mapper and trip host focused on practical city itineraries.",
        location="Kyoto, Japan",
        website="",
    ),
    "arun": DemoPublicProfile(
        username="arun",
        display_name="Arun N.",
        bio="Mountain route planner sharing first-light trekking ops playbooks.",
        location="El Chalten, Argentina",
        website="",
    ),
    "sahar": DemoPublicProfile(
        username="sahar",
        display_name="Sahar Belhadi",
        bio="Market-to-desert host combining cultural routes and practical logistics.",
        location="Marrakech, Morocco",
        website="",
    ),
}


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
        print(f"[accounts][verbose] {message}", flush=True)


def _safe_next_url(request: HttpRequest, fallback: str) -> str:
    """
    Accept user-provided next URL only if it targets the same host.
    """

    requested_next = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if not requested_next:
        return fallback

    allowed_hosts = {request.get_host()}
    if url_has_allowed_host_and_scheme(
        url=requested_next,
        allowed_hosts=allowed_hosts,
        require_https=request.is_secure(),
    ):
        return requested_next
    return fallback


def _safe_submitted_url(request: HttpRequest, submitted_url: str, fallback: str) -> str:
    candidate = submitted_url.strip()
    if not candidate:
        return fallback

    allowed_hosts = {request.get_host()}
    if url_has_allowed_host_and_scheme(
        url=candidate,
        allowed_hosts=allowed_hosts,
        require_https=request.is_secure(),
    ):
        return candidate
    return fallback


def _resolve_fallback_next_url(request: HttpRequest, fallback: str) -> str:
    """
    Resolve fallback next URL from current request context if possible.
    """

    referer = request.headers.get("Referer", "").strip()
    if not referer:
        return fallback

    allowed_hosts = {request.get_host()}
    if not url_has_allowed_host_and_scheme(
        url=referer,
        allowed_hosts=allowed_hosts,
        require_https=request.is_secure(),
    ):
        return fallback

    split_referer = urlsplit(referer)
    path = split_referer.path or "/"
    query = f"?{split_referer.query}" if split_referer.query else ""
    fragment = f"#{split_referer.fragment}" if split_referer.fragment else ""
    return f"{path}{query}{fragment}"


def _with_query_updates(
    url: str,
    updates: dict[str, str | None],
    remove: set[str] | None = None,
) -> str:
    split_target = urlsplit(url)
    query_pairs = dict(parse_qsl(split_target.query, keep_blank_values=True))

    for key in remove or set():
        query_pairs.pop(key, None)

    for key, value in updates.items():
        if value is None:
            query_pairs.pop(key, None)
        else:
            query_pairs[key] = value

    final_query = urlencode(query_pairs)
    return urlunsplit(
        (
            split_target.scheme,
            split_target.netloc,
            split_target.path,
            final_query,
            split_target.fragment,
        )
    )


def _strip_auth_modal_state(url: str) -> str:
    return _with_query_updates(url, updates={}, remove=AUTH_MODAL_QUERY_KEYS)


def _collect_form_error_messages(form: Any) -> dict[str, list[str]]:
    error_map: dict[str, list[str]] = {}

    for field_name, items in form.errors.get_json_data().items():
        key = "non_field" if field_name == "__all__" else str(field_name)
        messages_for_field: list[str] = []
        for item in items:
            message = str(item.get("message", "")).strip()
            if message:
                messages_for_field.append(message)

        if messages_for_field:
            error_map[key] = messages_for_field

    return error_map


def _set_auth_modal_feedback(
    request: HttpRequest,
    mode: str,
    form: Any,
    fields: dict[str, str],
) -> None:
    request.session[AUTH_MODAL_FEEDBACK_SESSION_KEY] = {
        "mode": mode,
        "fields": fields,
        "errors": _collect_form_error_messages(form),
    }


def _clear_auth_modal_feedback(request: HttpRequest) -> None:
    request.session.pop(AUTH_MODAL_FEEDBACK_SESSION_KEY, None)


def _auth_modal_redirect_target(
    origin_url: str,
    mode: str,
    reason: str = "",
    include_error: bool = False,
    next_url: str = "",
) -> str:
    normalized_reason = reason if reason == "continue" else ""
    safe_origin = _strip_auth_modal_state(origin_url)
    safe_next = _strip_auth_modal_state(next_url) if next_url else safe_origin
    include_next = safe_next != safe_origin

    updates: dict[str, str | None] = {"auth": mode}
    updates["auth_reason"] = normalized_reason if normalized_reason else None
    updates["auth_error"] = "1" if include_error else None
    updates["auth_next"] = safe_next if include_next else None
    return _with_query_updates(safe_origin, updates=updates)


def _profile_context_from_model(profile_user: ProfileUserLike, profile: AccountProfile) -> ProfilePayload:
    return {
        "username": profile_user.get_username(),
        "display_name": profile.effective_display_name,
        "bio": profile.bio or "No bio has been added yet.",
        "location": profile.location,
        "website": profile.website,
        "email": profile_user.email,
        "joined_at": profile_user.date_joined,
    }


def _profile_context_from_demo(demo_profile: DemoPublicProfile) -> ProfilePayload:
    return {
        "username": demo_profile.username,
        "display_name": demo_profile.display_name,
        "bio": demo_profile.bio,
        "location": demo_profile.location,
        "website": demo_profile.website,
        "email": "",
        "joined_at": None,
    }


@require_http_methods(["GET", "POST"])
def signup_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        messages.info(request, "You are already signed in.")
        return redirect(reverse("accounts:me"))

    origin_url = _resolve_fallback_next_url(request, reverse("home"))
    next_url = _safe_next_url(request, origin_url)
    reason = (request.POST.get("reason") or request.GET.get("reason") or "").strip().lower()

    if request.method == "GET":
        _clear_auth_modal_feedback(request)
        _vprint(request, "Signup GET redirected to shared auth modal")
        return redirect(
            _auth_modal_redirect_target(origin_url, "signup", reason=reason, next_url=next_url)
        )

    form = SignUpForm(request.POST)
    origin_url = _safe_submitted_url(
        request,
        request.POST.get("origin", ""),
        _resolve_fallback_next_url(request, reverse("home")),
    )
    next_url = _safe_submitted_url(request, request.POST.get("next", ""), origin_url)
    if form.is_valid():
        user = cast(ProfileUserLike, form.save())
        ensure_profile(user)
        login(request, cast(Any, user))
        _clear_auth_modal_feedback(request)
        _vprint(request, f"Signup succeeded for @{user.get_username()}")
        messages.success(request, "Welcome to tapne. Your account is ready.")
        return redirect(_strip_auth_modal_state(next_url))

    _set_auth_modal_feedback(
        request,
        "signup",
        form,
        {
            "username": str(request.POST.get("username", "")).strip(),
            "email": str(request.POST.get("email", "")).strip(),
        },
    )
    _vprint(request, f"Signup failed with {len(form.errors)} validation error block(s)")
    messages.error(request, "Could not sign up. Check details and try again.")
    return redirect(
        _auth_modal_redirect_target(
            origin_url,
            "signup",
            reason=reason,
            include_error=True,
            next_url=next_url,
        )
    )


@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        messages.info(request, "You are already logged in.")
        return redirect(reverse("accounts:me"))

    origin_url = _resolve_fallback_next_url(request, reverse("home"))
    next_url = _safe_next_url(request, origin_url)
    reason = (request.POST.get("reason") or request.GET.get("reason") or "").strip().lower()

    if request.method == "GET":
        _clear_auth_modal_feedback(request)
        _vprint(request, "Login GET redirected to shared auth modal")
        return redirect(
            _auth_modal_redirect_target(origin_url, "login", reason=reason, next_url=next_url)
        )

    form = LoginForm(request=request, data=request.POST)
    origin_url = _safe_submitted_url(
        request,
        request.POST.get("origin", ""),
        _resolve_fallback_next_url(request, reverse("home")),
    )
    next_url = _safe_submitted_url(request, request.POST.get("next", ""), origin_url)
    if form.is_valid():
        user = cast(ProfileUserLike, form.get_user())
        login(request, cast(Any, user))
        _clear_auth_modal_feedback(request)
        _vprint(request, f"Login succeeded for @{user.get_username()}")
        messages.success(request, "Welcome back.")
        return redirect(_strip_auth_modal_state(next_url))

    _set_auth_modal_feedback(
        request,
        "login",
        form,
        {"username": str(request.POST.get("username", "")).strip()},
    )
    _vprint(request, "Login failed due to invalid credentials or validation error")
    messages.error(request, "Invalid credentials. Please try again.")
    return redirect(
        _auth_modal_redirect_target(
            origin_url,
            "login",
            reason=reason,
            include_error=True,
            next_url=next_url,
        )
    )


@require_POST
def logout_view(request: HttpRequest) -> HttpResponse:
    next_url = _strip_auth_modal_state(_safe_next_url(request, reverse("home")))
    if request.user.is_authenticated:
        current_user = cast(ProfileUserLike, request.user)
        username = current_user.get_username()
        logout(request)
        _vprint(request, f"Logged out @{username}")
        messages.success(request, "You have been logged out.")
    else:
        _vprint(request, "Logout POST received from anonymous user")
        messages.info(request, "You are already logged out.")
    return redirect(next_url)


@login_required(login_url="accounts:login")
def my_profile_view(request: HttpRequest) -> HttpResponse:
    member_user = cast(ProfileUserLike, request.user)
    profile = ensure_profile(member_user)
    context: dict[str, object] = {
        "profile": _profile_context_from_model(member_user, profile),
    }
    _vprint(request, f"Loaded member profile page for @{member_user.get_username()}")
    return render(request, "pages/accounts/me.html", context)


@login_required(login_url="accounts:login")
@require_http_methods(["GET", "POST"])
def my_profile_edit_view(request: HttpRequest) -> HttpResponse:
    member_user = cast(ProfileUserLike, request.user)
    profile = ensure_profile(member_user)

    if request.method == "POST":
        form = ProfileEditForm(request.POST, instance=profile, user=cast(Any, request.user))
        if form.is_valid():
            form.save()
            _vprint(request, f"Profile update saved for @{member_user.get_username()}")
            messages.success(request, "Profile updated.")
            return redirect(reverse("accounts:me"))

        _vprint(request, "Profile update failed because submitted data was invalid")
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = ProfileEditForm(instance=profile, user=cast(Any, request.user))
        _vprint(request, f"Rendered profile edit form for @{member_user.get_username()}")

    return render(request, "pages/accounts/me_edit.html", {"form": form})


def public_profile_view(request: HttpRequest, username: str) -> HttpResponse:
    lookup_username = username.strip()
    profile_user = cast(ProfileUserLike | None, UserModel.objects.filter(username__iexact=lookup_username).first())

    is_demo_profile = False
    if profile_user:
        profile = ensure_profile(profile_user)
        profile_payload = _profile_context_from_model(profile_user, profile)
    else:
        demo_profile = DEMO_PUBLIC_PROFILES.get(lookup_username.lower())
        if not demo_profile:
            raise Http404("Profile not found.")

        is_demo_profile = True
        profile_payload = _profile_context_from_demo(demo_profile)

    viewer_is_member = bool(request.user.is_authenticated)
    viewer_username = str(getattr(request.user, "username", ""))
    is_owner = viewer_is_member and viewer_username.lower() == lookup_username.lower()
    profile_user_exists = profile_user is not None
    can_interact = viewer_is_member and not is_owner and profile_user_exists
    is_following_profile = False
    if can_interact and profile_user is not None:
        is_following_profile = is_following_user(
            follower=request.user,
            target_user=profile_user,
        )

    follow_stats = build_follow_stats_for_user(profile_user) if profile_user is not None else {"followers": 0}
    _vprint(
        request,
        (
            "Loaded public profile for @{username}; viewer_state={viewer}; demo_profile={demo}"
            .format(
                username=lookup_username,
                viewer="member" if viewer_is_member else "guest",
                demo=is_demo_profile,
            )
        ),
    )

    context: dict[str, object] = {
        "profile": profile_payload,
        "viewer_is_member": viewer_is_member,
        "can_interact": can_interact,
        "is_owner": is_owner,
        "is_demo_profile": is_demo_profile,
        "profile_user_exists": profile_user_exists,
        "is_following_profile": is_following_profile,
        "profile_followers_count": follow_stats["followers"],
    }
    return render(request, "pages/users/profile.html", context)
