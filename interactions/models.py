from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final, Literal, TypedDict, cast

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q
from django.db.models.constraints import BaseConstraint
from django.utils import timezone

from feed.models import get_blog_by_slug, get_demo_blogs, get_trip_by_id

CommentTargetType = Literal["trip", "blog"]
CommentSubmitOutcome = Literal[
    "member-required",
    "invalid-member",
    "invalid-target-type",
    "target-not-found",
    "empty-text",
    "too-long",
    "created",
]
ReplySubmitOutcome = Literal[
    "member-required",
    "invalid-member",
    "parent-not-found",
    "parent-not-top-level",
    "empty-text",
    "too-long",
    "created",
]
DMThreadOutcome = Literal[
    "member-required",
    "invalid-member",
    "self-thread-blocked",
    "created",
    "existing",
]
DMSendOutcome = Literal[
    "invalid-thread",
    "not-participant",
    "empty-message",
    "too-long",
    "sent",
]

ALLOWED_COMMENT_TARGET_TYPES: Final[set[str]] = {"trip", "blog"}


class CommentReplyData(TypedDict):
    id: int
    author_username: str
    text: str
    created_at: datetime


class CommentThreadData(TypedDict):
    id: int
    author_username: str
    text: str
    created_at: datetime
    reply_count: int
    replies: list[CommentReplyData]


class CommentThreadsPayload(TypedDict):
    comments: list[CommentThreadData]
    mode: str
    reason: str
    target_type: str
    target_key: str
    target_label: str
    target_url: str


class DMThreadPreviewData(TypedDict):
    id: int
    peer_username: str
    peer_url: str
    message_count: int
    last_message_preview: str
    last_message_at: datetime | None
    updated_at: datetime


class DMMessageData(TypedDict):
    id: int
    sender_username: str
    body: str
    created_at: datetime
    is_mine: bool


class DMInboxPayload(TypedDict):
    threads: list[DMThreadPreviewData]
    mode: str
    reason: str


class DMThreadPayload(TypedDict):
    thread: DMThreadPreviewData | None
    messages: list[DMMessageData]
    mode: str
    reason: str


@dataclass(frozen=True)
class CommentTargetResolution:
    target_type: CommentTargetType
    target_key: str
    target_label: str
    target_url: str


def _resolve_model(app_label: str, model_name: str) -> type[Any] | None:
    try:
        return cast(type[Any], apps.get_model(app_label, model_name))
    except LookupError:
        return None


def _trip_model() -> type[Any] | None:
    return _resolve_model("trips", "Trip")


def _blog_model() -> type[Any] | None:
    return _resolve_model("blogs", "Blog")


def _absolute_url(instance: object, *, fallback: str) -> str:
    get_absolute_url = getattr(instance, "get_absolute_url", None)
    if callable(get_absolute_url):
        try:
            maybe_url = get_absolute_url()
            if isinstance(maybe_url, str) and maybe_url.strip():
                return maybe_url
        except Exception:
            return fallback
    return fallback


def _trip_from_key(target_key: str) -> Any | None:
    if not target_key.isdigit():
        return None

    trip_model = _trip_model()
    if trip_model is None:
        return None

    return trip_model.objects.select_related("host").filter(pk=int(target_key)).first()


def _blog_from_key(target_key: str) -> Any | None:
    blog_model = _blog_model()
    if blog_model is None:
        return None

    if target_key.isdigit():
        by_pk = blog_model.objects.select_related("author").filter(pk=int(target_key)).first()
        if by_pk is not None:
            return by_pk

    return blog_model.objects.select_related("author").filter(slug__iexact=target_key).first()


def _clean_text(value: object) -> str:
    # Normalize whitespace so comparisons, seed idempotency, and rendering stay stable.
    return " ".join(str(value or "").strip().split())


def normalize_comment_target_type(raw_target_type: object) -> CommentTargetType | None:
    normalized = str(raw_target_type or "").strip().lower()
    if normalized in ALLOWED_COMMENT_TARGET_TYPES:
        return cast(CommentTargetType, normalized)
    return None


def normalize_comment_target_key(target_type: str, raw_target_id: object) -> str | None:
    normalized_type = normalize_comment_target_type(target_type)
    if normalized_type is None:
        return None

    raw_key = str(raw_target_id or "").strip()
    if not raw_key:
        return None

    if normalized_type == "trip":
        if not raw_key.isdigit():
            return None
        trip_id = int(raw_key)
        if trip_id <= 0:
            return None
        return str(trip_id)

    if normalized_type == "blog":
        return raw_key.lower()

    return None


def resolve_comment_target(
    target_type: str,
    raw_target_id: object,
) -> CommentTargetResolution | None:
    normalized_type = normalize_comment_target_type(target_type)
    if normalized_type is None:
        return None

    normalized_key = normalize_comment_target_key(normalized_type, raw_target_id)
    if normalized_key is None:
        return None

    if normalized_type == "trip":
        trip = _trip_from_key(normalized_key)
        if trip is not None:
            trip_id = int(getattr(trip, "pk", 0) or 0)
            if trip_id <= 0:
                return None
            trip_title = str(getattr(trip, "title", "") or "").strip() or f"Trip #{trip_id}"
            return CommentTargetResolution(
                target_type="trip",
                target_key=str(trip_id),
                target_label=trip_title,
                target_url=_absolute_url(trip, fallback=f"/trips/{trip_id}/"),
            )

        demo_trip = get_trip_by_id(int(normalized_key))
        if demo_trip is None:
            return None

        demo_trip_id = int(demo_trip.get("id", 0) or 0)
        return CommentTargetResolution(
            target_type="trip",
            target_key=str(demo_trip_id),
            target_label=str(demo_trip.get("title", "") or "").strip() or f"Trip #{demo_trip_id}",
            target_url=str(demo_trip.get("url", "") or "").strip() or f"/trips/{demo_trip_id}/",
        )

    blog = _blog_from_key(normalized_key)
    if blog is not None:
        slug = str(getattr(blog, "slug", "") or "").strip().lower()
        if not slug:
            return None
        title = str(getattr(blog, "title", "") or "").strip() or slug.replace("-", " ").title()
        return CommentTargetResolution(
            target_type="blog",
            target_key=slug,
            target_label=title,
            target_url=_absolute_url(blog, fallback=f"/blogs/{slug}/"),
        )

    if normalized_key.isdigit():
        demo_blog = next(
            (item for item in get_demo_blogs() if int(item.get("id", 0) or 0) == int(normalized_key)),
            None,
        )
    else:
        demo_blog = get_blog_by_slug(normalized_key)

    if demo_blog is None:
        return None

    demo_slug = str(demo_blog.get("slug", "") or "").strip().lower()
    if not demo_slug:
        return None

    demo_title = str(demo_blog.get("title", "") or "").strip() or demo_slug.replace("-", " ").title()
    return CommentTargetResolution(
        target_type="blog",
        target_key=demo_slug,
        target_label=demo_title,
        target_url=str(demo_blog.get("url", "") or "").strip() or f"/blogs/{demo_slug}/",
    )


class Comment(models.Model):
    """
    Unified comment row for top-level comments and one-level replies.

    The table keeps target metadata as canonical keys plus label/url snapshots
    so interactions remain readable even when a target row changes later.
    """

    TARGET_TRIP: Final[str] = "trip"
    TARGET_BLOG: Final[str] = "blog"
    TARGET_TYPE_CHOICES: Final[tuple[tuple[str, str], ...]] = (
        (TARGET_TRIP, "Trip"),
        (TARGET_BLOG, "Blog"),
    )
    TEXT_MAX_LENGTH: Final[int] = 2_000

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="interaction_comments",
    )
    target_type = models.CharField(max_length=12, choices=TARGET_TYPE_CHOICES)
    target_key = models.CharField(max_length=191)
    target_label = models.CharField(max_length=255, blank=True)
    target_url = models.CharField(max_length=255, blank=True)
    text = models.CharField(max_length=TEXT_MAX_LENGTH)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="replies",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    if TYPE_CHECKING:
        parent_id: int | None
        replies: models.Manager[Comment]

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(
                fields=("target_type", "target_key", "parent", "created_at"),
                name="interact_comment_target_idx",
            ),
            models.Index(fields=("author", "created_at"), name="interact_comment_author_idx"),
        ]
        constraints: list[BaseConstraint] = [
            cast(
                BaseConstraint,
                models.CheckConstraint(
                    condition=~Q(pk=F("parent_id")),
                    name="interact_comment_no_self_parent",
                ),
            )
        ]

    def __str__(self) -> str:
        author_username = str(getattr(self.author, "username", "") or "").strip()
        target = f"{self.target_type}:{self.target_key}"
        return f"Comment #{self.pk or 'new'} by @{author_username} on {target}"

    @property
    def is_reply(self) -> bool:
        return self.parent_id is not None

    def clean(self) -> None:
        super().clean()

        cleaned_text = _clean_text(self.text)
        if not cleaned_text:
            raise ValidationError({"text": "Comment text cannot be empty."})

        if len(cleaned_text) > self.TEXT_MAX_LENGTH:
            raise ValidationError(
                {"text": f"Comment text must be {self.TEXT_MAX_LENGTH} characters or fewer."}
            )

        self.text = cleaned_text
        if self.parent_id is None:
            return

        parent = Comment.objects.select_related("parent").filter(pk=self.parent_id).first()
        if parent is None:
            raise ValidationError({"parent": "Parent comment does not exist."})

        if parent.parent_id is not None:
            raise ValidationError({"parent": "Replies can only be attached to top-level comments."})

        if parent.target_type != self.target_type or parent.target_key != self.target_key:
            raise ValidationError(
                {"parent": "Reply target must match the parent comment target."}
            )

    def to_reply_data(self) -> CommentReplyData:
        return {
            "id": int(self.pk or 0),
            "author_username": str(getattr(self.author, "username", "") or "").strip(),
            "text": str(self.text or "").strip(),
            "created_at": self.created_at,
        }


class DirectMessageThread(models.Model):
    """
    Private one-to-one member thread model.

    Pair ordering (`member_one_id < member_two_id`) keeps the table canonical
    and allows idempotent `get_or_create` thread lookup.
    """

    member_one = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dm_threads_as_member_one",
    )
    member_two = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dm_threads_as_member_two",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    if TYPE_CHECKING:
        member_one_id: int
        member_two_id: int
        messages: models.Manager[DirectMessage]

    class Meta:
        ordering = ("-updated_at", "-id")
        constraints: list[BaseConstraint] = [
            cast(
                BaseConstraint,
                models.UniqueConstraint(
                    fields=("member_one", "member_two"),
                    name="interact_dm_unique_pair",
                ),
            ),
            cast(
                BaseConstraint,
                models.CheckConstraint(
                    condition=~Q(member_one=F("member_two")),
                    name="interact_dm_no_self",
                ),
            ),
            cast(
                BaseConstraint,
                models.CheckConstraint(
                    condition=Q(member_one__lt=F("member_two")),
                    name="interact_dm_pair_order",
                ),
            ),
        ]
        indexes = [
            models.Index(fields=("member_one", "updated_at"), name="interact_dm_one_upd_idx"),
            models.Index(fields=("member_two", "updated_at"), name="interact_dm_two_upd_idx"),
        ]

    def __str__(self) -> str:
        username_one = str(getattr(self.member_one, "username", "") or "").strip()
        username_two = str(getattr(self.member_two, "username", "") or "").strip()
        return f"DM thread @{username_one} <-> @{username_two}"

    def get_absolute_url(self) -> str:
        return f"/interactions/dm/{self.pk}/"

    def is_participant(self, member: object) -> bool:
        member_id = int(getattr(member, "pk", 0) or 0)
        if member_id <= 0:
            return False
        return member_id in {int(self.member_one_id), int(self.member_two_id)}

    def other_participant(self, member: object) -> object | None:
        member_id = int(getattr(member, "pk", 0) or 0)
        if member_id <= 0:
            return None
        if member_id == int(self.member_one_id):
            return self.member_two
        if member_id == int(self.member_two_id):
            return self.member_one
        return None

    def touch(self) -> None:
        self.updated_at = timezone.now()
        self.save(update_fields=["updated_at"])


class DirectMessage(models.Model):
    """
    Message rows for direct two-member threads.
    """

    BODY_MAX_LENGTH: Final[int] = 4_000

    thread = models.ForeignKey(
        DirectMessageThread,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_direct_messages",
    )
    body = models.CharField(max_length=BODY_MAX_LENGTH)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    if TYPE_CHECKING:
        thread_id: int
        sender_id: int

    class Meta:
        ordering = ("created_at", "id")
        indexes = [
            models.Index(fields=("thread", "created_at"), name="interact_dmsg_thread_idx"),
            models.Index(fields=("sender", "created_at"), name="interact_dmsg_sender_idx"),
        ]

    def __str__(self) -> str:
        sender_username = str(getattr(self.sender, "username", "") or "").strip()
        return f"DM #{self.pk or 'new'} in thread #{self.thread_id} by @{sender_username}"

    def clean(self) -> None:
        super().clean()

        cleaned_body = _clean_text(self.body)
        if not cleaned_body:
            raise ValidationError({"body": "Message text cannot be empty."})

        if len(cleaned_body) > self.BODY_MAX_LENGTH:
            raise ValidationError(
                {"body": f"Message text must be {self.BODY_MAX_LENGTH} characters or fewer."}
            )

        if self.thread_id and self.sender_id and not self.thread.is_participant(self.sender):
            raise ValidationError({"sender": "Sender must be a participant in this thread."})

        self.body = cleaned_body

    def to_message_data(self, *, viewer_id: int) -> DMMessageData:
        sender_username = str(getattr(self.sender, "username", "") or "").strip()
        return {
            "id": int(self.pk or 0),
            "sender_username": sender_username,
            "body": str(self.body or "").strip(),
            "created_at": self.created_at,
            "is_mine": int(self.sender_id) == int(viewer_id),
        }


def _ordered_member_pair(member: object, other_member: object) -> tuple[Any, Any] | None:
    member_id = int(getattr(member, "pk", 0) or 0)
    other_member_id = int(getattr(other_member, "pk", 0) or 0)
    if member_id <= 0 or other_member_id <= 0:
        return None
    if member_id == other_member_id:
        return None

    typed_member = cast(Any, member)
    typed_other_member = cast(Any, other_member)
    if member_id < other_member_id:
        return typed_member, typed_other_member
    return typed_other_member, typed_member


def submit_comment(
    *,
    member: object,
    target_type: object,
    target_id: object,
    text: object,
) -> tuple[Comment | None, CommentSubmitOutcome, CommentTargetResolution | None]:
    if not bool(getattr(member, "is_authenticated", False)):
        return None, "member-required", None

    member_id = int(getattr(member, "pk", 0) or 0)
    if member_id <= 0:
        return None, "invalid-member", None

    resolved_target = resolve_comment_target(str(target_type or ""), target_id)
    if resolved_target is None:
        if normalize_comment_target_type(target_type) is None:
            return None, "invalid-target-type", None
        return None, "target-not-found", None

    cleaned_text = _clean_text(text)
    if not cleaned_text:
        return None, "empty-text", resolved_target
    if len(cleaned_text) > Comment.TEXT_MAX_LENGTH:
        return None, "too-long", resolved_target

    comment = Comment.objects.create(
        author=cast(Any, member),
        target_type=resolved_target.target_type,
        target_key=resolved_target.target_key,
        target_label=resolved_target.target_label,
        target_url=resolved_target.target_url,
        text=cleaned_text,
        parent=None,
    )
    return comment, "created", resolved_target


def submit_reply(
    *,
    member: object,
    comment_id: object,
    text: object,
) -> tuple[Comment | None, ReplySubmitOutcome, Comment | None]:
    if not bool(getattr(member, "is_authenticated", False)):
        return None, "member-required", None

    member_id = int(getattr(member, "pk", 0) or 0)
    if member_id <= 0:
        return None, "invalid-member", None

    raw_comment_id = str(comment_id or "").strip()
    if not raw_comment_id.isdigit():
        return None, "parent-not-found", None

    parent = Comment.objects.select_related("author").filter(pk=int(raw_comment_id)).first()
    if parent is None:
        return None, "parent-not-found", None
    if parent.parent_id is not None:
        return None, "parent-not-top-level", parent

    cleaned_text = _clean_text(text)
    if not cleaned_text:
        return None, "empty-text", parent
    if len(cleaned_text) > Comment.TEXT_MAX_LENGTH:
        return None, "too-long", parent

    reply = Comment.objects.create(
        author=cast(Any, member),
        target_type=parent.target_type,
        target_key=parent.target_key,
        target_label=parent.target_label,
        target_url=parent.target_url,
        text=cleaned_text,
        parent=parent,
    )
    return reply, "created", parent


def build_comment_threads_payload_for_target(
    *,
    target_type: object,
    target_id: object,
    limit: int = 50,
    reply_limit: int = 8,
) -> CommentThreadsPayload:
    resolved_target = resolve_comment_target(str(target_type or ""), target_id)
    if resolved_target is None:
        return {
            "comments": [],
            "mode": "invalid-target",
            "reason": "Comments are unavailable because this target could not be resolved.",
            "target_type": str(target_type or "").strip().lower(),
            "target_key": str(target_id or "").strip().lower(),
            "target_label": "Unavailable",
            "target_url": "#",
        }

    effective_limit = max(1, int(limit or 50))
    effective_reply_limit = max(1, int(reply_limit or 8))

    top_level_rows = list(
        Comment.objects.select_related("author")
        .filter(
            target_type=resolved_target.target_type,
            target_key=resolved_target.target_key,
            parent__isnull=True,
        )
        .order_by("-created_at", "-pk")[:effective_limit]
    )

    parent_ids = [int(item.pk) for item in top_level_rows if int(item.pk or 0) > 0]
    replies_by_parent: dict[int, list[CommentReplyData]] = {}
    if parent_ids:
        reply_rows = (
            Comment.objects.select_related("author")
            .filter(parent_id__in=parent_ids)
            .order_by("created_at", "pk")
        )
        for reply in reply_rows:
            parent_id = int(getattr(reply, "parent_id", 0) or 0)
            if parent_id <= 0:
                continue
            bucket = replies_by_parent.setdefault(parent_id, [])
            if len(bucket) >= effective_reply_limit:
                continue
            bucket.append(reply.to_reply_data())

    comments: list[CommentThreadData] = []
    for row in top_level_rows:
        row_id = int(row.pk or 0)
        replies = replies_by_parent.get(row_id, [])
        comments.append(
            {
                "id": row_id,
                "author_username": str(getattr(row.author, "username", "") or "").strip(),
                "text": str(row.text or "").strip(),
                "created_at": row.created_at,
                "reply_count": row.replies.count(),
                "replies": replies,
            }
        )

    reason = "Comments are ordered from newest to oldest."
    if not comments:
        reason = "No comments yet. Start the conversation."

    return {
        "comments": comments,
        "mode": "target-comments",
        "reason": reason,
        "target_type": resolved_target.target_type,
        "target_key": resolved_target.target_key,
        "target_label": resolved_target.target_label,
        "target_url": resolved_target.target_url,
    }


def get_or_create_dm_thread_for_members(
    *,
    member: object,
    other_member: object,
) -> tuple[DirectMessageThread | None, bool, DMThreadOutcome]:
    if not bool(getattr(member, "is_authenticated", False)):
        return None, False, "member-required"

    pair = _ordered_member_pair(member, other_member)
    if pair is None:
        member_id = int(getattr(member, "pk", 0) or 0)
        other_member_id = int(getattr(other_member, "pk", 0) or 0)
        if member_id <= 0 or other_member_id <= 0:
            return None, False, "invalid-member"
        return None, False, "self-thread-blocked"

    member_one, member_two = pair
    thread, created = DirectMessageThread.objects.get_or_create(
        member_one=member_one,
        member_two=member_two,
    )
    return thread, created, ("created" if created else "existing")


def send_dm_message(
    *,
    thread: DirectMessageThread | None,
    sender: object,
    body: object,
) -> tuple[DirectMessage | None, DMSendOutcome]:
    if thread is None:
        return None, "invalid-thread"

    if not thread.is_participant(sender):
        return None, "not-participant"

    cleaned_body = _clean_text(body)
    if not cleaned_body:
        return None, "empty-message"
    if len(cleaned_body) > DirectMessage.BODY_MAX_LENGTH:
        return None, "too-long"

    with transaction.atomic():
        message = DirectMessage.objects.create(
            thread=thread,
            sender=cast(Any, sender),
            body=cleaned_body,
        )
        thread.touch()

    return message, "sent"


def _thread_preview_data(thread: DirectMessageThread, *, viewer: object) -> DMThreadPreviewData:
    peer = thread.other_participant(viewer)
    peer_username = str(getattr(peer, "username", "") or "").strip() or "unknown"
    last_message = thread.messages.order_by("-created_at", "-pk").first()
    last_message_preview = ""
    last_message_at: datetime | None = None
    if last_message is not None:
        last_message_preview = str(getattr(last_message, "body", "") or "").strip()
        if len(last_message_preview) > 120:
            last_message_preview = f"{last_message_preview[:117].rstrip()}..."
        last_message_at = cast(datetime | None, getattr(last_message, "created_at", None))

    return {
        "id": int(thread.pk or 0),
        "peer_username": peer_username,
        "peer_url": f"/u/{peer_username}/",
        "message_count": int(thread.messages.count()),
        "last_message_preview": last_message_preview,
        "last_message_at": last_message_at,
        "updated_at": thread.updated_at,
    }


def _thread_queryset_for_member(member: object) -> models.QuerySet[DirectMessageThread]:
    member_id = int(getattr(member, "pk", 0) or 0)
    return DirectMessageThread.objects.select_related("member_one", "member_two").filter(
        Q(member_one_id=member_id) | Q(member_two_id=member_id)
    )


def build_dm_inbox_payload_for_member(
    member: object,
    *,
    limit: int = 30,
) -> DMInboxPayload:
    if not bool(getattr(member, "is_authenticated", False)):
        return {
            "threads": [],
            "mode": "guest-not-allowed",
            "reason": "Direct messages are available for members only.",
        }

    member_id = int(getattr(member, "pk", 0) or 0)
    if member_id <= 0:
        return {
            "threads": [],
            "mode": "member-dm-inbox",
            "reason": "No message threads are available for this account.",
        }

    effective_limit = max(1, int(limit or 30))
    thread_rows = list(_thread_queryset_for_member(member).order_by("-updated_at", "-pk")[:effective_limit])
    thread_previews = [_thread_preview_data(thread, viewer=member) for thread in thread_rows]

    reason = "Threads are ordered by most recent message activity."
    if not thread_previews:
        reason = "No conversations yet. Start a thread from a member profile."

    return {
        "threads": thread_previews,
        "mode": "member-dm-inbox",
        "reason": reason,
    }


def build_dm_thread_payload_for_member(
    member: object,
    *,
    thread_id: int,
    limit: int = 200,
) -> DMThreadPayload:
    if not bool(getattr(member, "is_authenticated", False)):
        return {
            "thread": None,
            "messages": [],
            "mode": "guest-not-allowed",
            "reason": "Direct messages are available for members only.",
        }

    thread = _thread_queryset_for_member(member).filter(pk=thread_id).first()
    if thread is None:
        return {
            "thread": None,
            "messages": [],
            "mode": "thread-not-found",
            "reason": "This thread was not found or is not available to the current member.",
        }

    effective_limit = max(1, int(limit or 200))
    viewer_id = int(getattr(member, "pk", 0) or 0)
    message_rows = list(
        DirectMessage.objects.select_related("sender")
        .filter(thread=thread)
        .order_by("created_at", "pk")[:effective_limit]
    )
    messages = [message.to_message_data(viewer_id=viewer_id) for message in message_rows]
    reason = "Thread messages are ordered oldest to newest."
    if not messages:
        reason = "No messages yet. Send the first message."

    return {
        "thread": _thread_preview_data(thread, viewer=member),
        "messages": messages,
        "mode": "member-dm-thread",
        "reason": reason,
    }
