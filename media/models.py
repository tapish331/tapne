from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final, Literal, TypedDict, cast

from PIL import Image, UnidentifiedImageError
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import models
from django.db.models import Q
from django.db.models.constraints import BaseConstraint
from django.utils import timezone

MediaTargetType = Literal["trip", "blog", "review"]
MediaKind = Literal["image", "video"]
MediaUploadOutcome = Literal[
    "member-required",
    "invalid-member",
    "missing-file",
    "invalid-target-type",
    "target-not-found",
    "permission-denied",
    "empty-file",
    "invalid-content-type",
    "file-too-large",
    "invalid-image",
    "too-long-caption",
    "already-attached",
    "attached-existing",
    "created",
]
MediaDeleteOutcome = Literal[
    "member-required",
    "invalid-member",
    "not-found",
    "permission-denied",
    "deleted-attachment",
    "deleted-attachment-and-asset",
]

ALLOWED_MEDIA_TARGET_TYPES: Final[set[str]] = {"trip", "blog", "review"}
DEFAULT_ALLOWED_IMAGE_MIME_TYPES: Final[tuple[str, ...]] = (
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
)
DEFAULT_ALLOWED_VIDEO_MIME_TYPES: Final[tuple[str, ...]] = (
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-m4v",
)
DEFAULT_ALLOWED_IMAGE_EXTENSIONS: Final[tuple[str, ...]] = (
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
)
DEFAULT_ALLOWED_VIDEO_EXTENSIONS: Final[tuple[str, ...]] = (
    ".mp4",
    ".mov",
    ".webm",
    ".m4v",
)
DEFAULT_IMAGE_MAX_MB: Final[int] = 12
DEFAULT_VIDEO_MAX_MB: Final[int] = 100


class MediaAttachmentData(TypedDict):
    id: int
    asset_id: int
    owner_username: str
    kind: str
    content_type: str
    file_url: str
    filename: str
    size_bytes: int
    size_label: str
    caption: str
    target_type: str
    target_key: str
    target_label: str
    target_url: str
    created_at: datetime
    is_mine: bool
    can_manage: bool


class MediaTargetPayload(TypedDict):
    attachments: list[MediaAttachmentData]
    mode: str
    reason: str
    target_type: str
    target_key: str
    target_label: str
    target_url: str
    can_upload: bool


@dataclass(frozen=True)
class MediaTargetResolution:
    target_type: MediaTargetType
    target_key: str
    target_label: str
    target_url: str
    owner_id: int


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_slug(value: object) -> str:
    return str(value or "").strip().lower()


def _read_str_set_setting(setting_name: str, default_values: tuple[str, ...]) -> set[str]:
    raw_value: object = getattr(settings, setting_name, default_values)
    candidates: list[str]

    if isinstance(raw_value, str):
        candidates = raw_value.split(",")
    elif isinstance(raw_value, (list, tuple, set)):
        typed_values = cast(list[object] | tuple[object, ...] | set[object], raw_value)
        candidates = [("" if value is None else str(value)) for value in typed_values]
    else:
        candidates = list(default_values)

    normalized = {
        item.strip().lower()
        for item in candidates
        if item.strip()
    }
    if normalized:
        return normalized

    return {value.lower() for value in default_values}


def _read_megabytes_setting(setting_name: str, default_value: int) -> int:
    raw_value = getattr(settings, setting_name, default_value)
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        parsed = int(default_value)
    return max(1, parsed)


def _max_bytes_for_kind(kind: MediaKind) -> int:
    max_megabytes = (
        _read_megabytes_setting("TAPNE_MEDIA_IMAGE_MAX_MB", DEFAULT_IMAGE_MAX_MB)
        if kind == "image"
        else _read_megabytes_setting("TAPNE_MEDIA_VIDEO_MAX_MB", DEFAULT_VIDEO_MAX_MB)
    )
    return max_megabytes * 1024 * 1024


def _allowed_mime_types_for_kind(kind: MediaKind) -> set[str]:
    if kind == "image":
        return _read_str_set_setting(
            "TAPNE_MEDIA_ALLOWED_IMAGE_MIME_TYPES",
            DEFAULT_ALLOWED_IMAGE_MIME_TYPES,
        )
    return _read_str_set_setting(
        "TAPNE_MEDIA_ALLOWED_VIDEO_MIME_TYPES",
        DEFAULT_ALLOWED_VIDEO_MIME_TYPES,
    )


def _allowed_extensions_for_kind(kind: MediaKind) -> set[str]:
    if kind == "image":
        return _read_str_set_setting(
            "TAPNE_MEDIA_ALLOWED_IMAGE_EXTENSIONS",
            DEFAULT_ALLOWED_IMAGE_EXTENSIONS,
        )
    return _read_str_set_setting(
        "TAPNE_MEDIA_ALLOWED_VIDEO_EXTENSIONS",
        DEFAULT_ALLOWED_VIDEO_EXTENSIONS,
    )


def _human_size(size_bytes: int) -> str:
    value = float(max(0, int(size_bytes or 0)))
    units = ("B", "KB", "MB", "GB")
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{int(value)} {units[unit_index]}"
    return f"{value:.1f} {units[unit_index]}"


def _safe_tell(uploaded_file: UploadedFile) -> int | None:
    try:
        return int(uploaded_file.tell())
    except Exception:
        return None


def _reset_file_position(uploaded_file: UploadedFile, position: int | None) -> None:
    if position is None:
        return
    try:
        uploaded_file.seek(position)
    except Exception:
        return


def _sha256_for_uploaded_file(uploaded_file: UploadedFile) -> str:
    position = _safe_tell(uploaded_file)
    try:
        if position is not None:
            uploaded_file.seek(0)
        hasher = hashlib.sha256()
        for chunk in uploaded_file.chunks():
            hasher.update(chunk)
        return hasher.hexdigest()
    finally:
        _reset_file_position(uploaded_file, position)


def _extract_image_dimensions(uploaded_file: UploadedFile) -> tuple[int | None, int | None]:
    position = _safe_tell(uploaded_file)
    try:
        if position is not None:
            uploaded_file.seek(0)

        with Image.open(uploaded_file) as image:
            image.verify()

        if position is not None:
            uploaded_file.seek(0)

        with Image.open(uploaded_file) as image:
            width, height = image.size
            return int(width), int(height)
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        return None, None
    finally:
        _reset_file_position(uploaded_file, position)


def _declared_or_guessed_content_type(uploaded_file: UploadedFile) -> str:
    declared = str(getattr(uploaded_file, "content_type", "") or "").split(";", 1)[0].strip().lower()
    if declared:
        return declared

    guessed, _encoding = mimetypes.guess_type(str(getattr(uploaded_file, "name", "") or ""))
    return str(guessed or "").strip().lower()


def _upload_extension(uploaded_file: UploadedFile) -> str:
    return Path(str(getattr(uploaded_file, "name", "") or "")).suffix.lower()


def _classify_upload(uploaded_file: UploadedFile) -> tuple[MediaKind | None, str, MediaUploadOutcome | None]:
    content_type = _declared_or_guessed_content_type(uploaded_file)
    extension = _upload_extension(uploaded_file)

    kind: MediaKind | None = None
    if content_type.startswith("image/") or extension in _allowed_extensions_for_kind("image"):
        kind = "image"
    elif content_type.startswith("video/") or extension in _allowed_extensions_for_kind("video"):
        kind = "video"

    if kind is None:
        return None, content_type, "invalid-content-type"

    allowed_extensions = _allowed_extensions_for_kind(kind)
    allowed_mime_types = _allowed_mime_types_for_kind(kind)

    if extension and extension not in allowed_extensions:
        return None, content_type, "invalid-content-type"

    if content_type and content_type not in allowed_mime_types:
        if content_type not in {"application/octet-stream", "binary/octet-stream"}:
            return None, content_type, "invalid-content-type"

        guessed, _encoding = mimetypes.guess_type(str(getattr(uploaded_file, "name", "") or ""))
        guessed_content_type = str(guessed or "").strip().lower()
        if not guessed_content_type or guessed_content_type not in allowed_mime_types:
            return None, content_type, "invalid-content-type"
        content_type = guessed_content_type

    if not content_type:
        content_type = "image/jpeg" if kind == "image" else "video/mp4"

    return kind, content_type, None


def _resolve_model(app_label: str, model_name: str) -> type[Any] | None:
    try:
        return cast(type[Any], apps.get_model(app_label, model_name))
    except LookupError:
        return None


def _trip_model() -> type[Any] | None:
    return _resolve_model("trips", "Trip")


def _blog_model() -> type[Any] | None:
    return _resolve_model("blogs", "Blog")


def _review_model() -> type[Any] | None:
    return _resolve_model("reviews", "Review")


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
        blog_by_pk = blog_model.objects.select_related("author").filter(pk=int(target_key)).first()
        if blog_by_pk is not None:
            return blog_by_pk

    return blog_model.objects.select_related("author").filter(slug__iexact=target_key).first()


def _review_from_key(target_key: str) -> Any | None:
    if not target_key.isdigit():
        return None

    review_model = _review_model()
    if review_model is None:
        return None

    return review_model.objects.select_related("author").filter(pk=int(target_key)).first()


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


def normalize_media_target_type(raw_target_type: object) -> MediaTargetType | None:
    normalized = str(raw_target_type or "").strip().lower()
    if normalized in ALLOWED_MEDIA_TARGET_TYPES:
        return cast(MediaTargetType, normalized)
    return None


def normalize_media_target_key(target_type: object, raw_target_id: object) -> str | None:
    normalized_type = normalize_media_target_type(target_type)
    if normalized_type is None:
        return None

    raw_key = str(raw_target_id or "").strip()
    if not raw_key:
        return None

    if normalized_type in {"trip", "review"}:
        if not raw_key.isdigit():
            return None
        parsed_id = int(raw_key)
        if parsed_id <= 0:
            return None
        return str(parsed_id)

    if normalized_type == "blog":
        return _normalize_slug(raw_key)

    return None


def resolve_media_target(
    target_type: object,
    raw_target_id: object,
) -> MediaTargetResolution | None:
    normalized_type = normalize_media_target_type(target_type)
    if normalized_type is None:
        return None

    normalized_key = normalize_media_target_key(normalized_type, raw_target_id)
    if normalized_key is None:
        return None

    if normalized_type == "trip":
        trip = _trip_from_key(normalized_key)
        if trip is None:
            return None

        trip_id = int(getattr(trip, "pk", 0) or 0)
        owner_id = int(getattr(trip, "host_id", 0) or 0)
        if trip_id <= 0 or owner_id <= 0:
            return None

        trip_title = str(getattr(trip, "title", "") or "").strip() or f"Trip #{trip_id}"
        return MediaTargetResolution(
            target_type="trip",
            target_key=str(trip_id),
            target_label=trip_title,
            target_url=_absolute_url(trip, fallback=f"/trips/{trip_id}/"),
            owner_id=owner_id,
        )

    if normalized_type == "blog":
        blog = _blog_from_key(normalized_key)
        if blog is None:
            return None

        slug = _normalize_slug(getattr(blog, "slug", ""))
        owner_id = int(getattr(blog, "author_id", 0) or 0)
        if not slug or owner_id <= 0:
            return None

        blog_title = str(getattr(blog, "title", "") or "").strip() or slug.replace("-", " ").title()
        return MediaTargetResolution(
            target_type="blog",
            target_key=slug,
            target_label=blog_title,
            target_url=_absolute_url(blog, fallback=f"/blogs/{slug}/"),
            owner_id=owner_id,
        )

    review = _review_from_key(normalized_key)
    if review is None:
        return None

    review_id = int(getattr(review, "pk", 0) or 0)
    owner_id = int(getattr(review, "author_id", 0) or 0)
    if review_id <= 0 or owner_id <= 0:
        return None

    author_username = str(getattr(getattr(review, "author", None), "username", "") or "").strip()
    headline = _clean_text(getattr(review, "headline", ""))
    target_label = headline or (f"Review by @{author_username}" if author_username else f"Review #{review_id}")

    target_url = str(getattr(review, "target_url", "") or "").strip()
    if target_url and "#" not in target_url:
        target_url = f"{target_url}#reviews"
    if not target_url:
        target_url = "/"

    return MediaTargetResolution(
        target_type="review",
        target_key=str(review_id),
        target_label=target_label,
        target_url=target_url,
        owner_id=owner_id,
    )


def media_upload_to(_instance: MediaAsset, filename: str) -> str:
    safe_name = Path(filename or "upload.bin").name
    extension = Path(safe_name).suffix.lower()
    now = timezone.localtime(timezone.now())
    entropy = hashlib.sha1(f"{now.timestamp()}:{safe_name}".encode("utf-8")).hexdigest()[:20]
    return f"uploads/{now:%Y/%m/%d}/{entropy}{extension}"


class MediaAsset(models.Model):
    """
    Canonical uploaded file row persisted via Django's storage abstraction.

    `file` uses the default storage backend, which can be MinIO/GCS in
    production-faithful configurations and filesystem in fallback mode.
    """

    KIND_IMAGE: Final[str] = "image"
    KIND_VIDEO: Final[str] = "video"
    KIND_CHOICES: Final[tuple[tuple[str, str], ...]] = (
        (KIND_IMAGE, "Image"),
        (KIND_VIDEO, "Video"),
    )
    CAPTION_MAX_LENGTH: Final[int] = 280

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="media_assets",
    )
    file = models.FileField(upload_to=media_upload_to)
    kind = models.CharField(max_length=12, choices=KIND_CHOICES)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=127, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    checksum_sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    width_px = models.PositiveIntegerField(blank=True, null=True)
    height_px = models.PositiveIntegerField(blank=True, null=True)
    caption = models.CharField(max_length=CAPTION_MAX_LENGTH, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=("owner", "created_at"), name="media_asset_owner_created_idx"),
            models.Index(fields=("kind", "created_at"), name="media_asset_kind_created_idx"),
        ]

    def __str__(self) -> str:
        owner_username = str(getattr(self.owner, "username", "") or "").strip()
        return f"MediaAsset #{self.pk or 'new'} ({self.kind}) by @{owner_username}"

    def clean(self) -> None:
        super().clean()

        self.original_name = Path(str(self.original_name or "upload.bin")).name
        self.content_type = str(self.content_type or "").strip().lower()
        self.caption = _clean_text(self.caption)

        if self.kind not in {self.KIND_IMAGE, self.KIND_VIDEO}:
            raise ValidationError({"kind": "Unsupported media kind."})

        if int(self.size_bytes or 0) <= 0:
            raise ValidationError({"size_bytes": "Uploaded file cannot be empty."})

        if len(self.caption) > self.CAPTION_MAX_LENGTH:
            raise ValidationError(
                {"caption": f"Caption must be {self.CAPTION_MAX_LENGTH} characters or fewer."}
            )

    def to_attachment_data(self, *, attachment: MediaAttachment, viewer_id: int) -> MediaAttachmentData:
        owner_username = str(getattr(self.owner, "username", "") or "").strip()
        file_url = ""
        try:
            file_url = str(self.file.url or "")
        except Exception:
            file_url = ""

        viewer_matches_owner = int(getattr(self, "owner_id", 0) or 0) == int(viewer_id)
        return {
            "id": int(attachment.pk or 0),
            "asset_id": int(self.pk or 0),
            "owner_username": owner_username,
            "kind": str(self.kind or "").strip().lower(),
            "content_type": str(self.content_type or "").strip().lower(),
            "file_url": file_url,
            "filename": str(self.original_name or "").strip(),
            "size_bytes": int(self.size_bytes or 0),
            "size_label": _human_size(int(self.size_bytes or 0)),
            "caption": str(self.caption or "").strip(),
            "target_type": str(attachment.target_type or "").strip().lower(),
            "target_key": str(attachment.target_key or "").strip(),
            "target_label": str(attachment.target_label or "").strip(),
            "target_url": str(attachment.target_url or "").strip(),
            "created_at": attachment.created_at,
            "is_mine": viewer_matches_owner,
            "can_manage": viewer_matches_owner,
        }


class MediaAttachment(models.Model):
    """
    Attachment mapping between a media asset and domain targets.

    Targets are normalized into `(target_type, target_key)` so trips/blogs/reviews
    can share one persistence model without generic foreign keys.
    """

    TARGET_TRIP: Final[str] = "trip"
    TARGET_BLOG: Final[str] = "blog"
    TARGET_REVIEW: Final[str] = "review"
    TARGET_TYPE_CHOICES: Final[tuple[tuple[str, str], ...]] = (
        (TARGET_TRIP, "Trip"),
        (TARGET_BLOG, "Blog"),
        (TARGET_REVIEW, "Review"),
    )

    asset = models.ForeignKey(
        MediaAsset,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    target_type = models.CharField(max_length=16, choices=TARGET_TYPE_CHOICES)
    target_key = models.CharField(max_length=191)
    target_label = models.CharField(max_length=255, blank=True)
    target_url = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints: list[BaseConstraint] = [
            cast(
                BaseConstraint,
                models.UniqueConstraint(
                    fields=("asset", "target_type", "target_key"),
                    name="media_unique_asset_target",
                ),
            ),
            cast(
                BaseConstraint,
                models.CheckConstraint(
                    condition=Q(target_type__in=("trip", "blog", "review")),
                    name="media_attachment_target_type_allowed",
                ),
            ),
        ]
        indexes = [
            models.Index(fields=("target_type", "target_key", "created_at"), name="media_target_created_idx"),
            models.Index(fields=("asset", "created_at"), name="media_asset_created_idx"),
        ]

    def __str__(self) -> str:
        return f"MediaAttachment #{self.pk or 'new'} -> {self.target_type}:{self.target_key}"

    def clean(self) -> None:
        super().clean()

        normalized_type = normalize_media_target_type(self.target_type)
        normalized_key = normalize_media_target_key(normalized_type or "", self.target_key)
        if normalized_type is None or normalized_key is None:
            raise ValidationError({"target_key": "Invalid media target identifier."})

        self.target_type = normalized_type
        self.target_key = normalized_key
        self.target_label = _clean_text(self.target_label)
        self.target_url = str(self.target_url or "").strip()


def build_media_attachment_map_for_targets(
    *,
    target_type: object,
    target_ids: list[object],
    viewer: object,
    limit_per_target: int = 6,
) -> dict[str, list[MediaAttachmentData]]:
    normalized_type = normalize_media_target_type(target_type)
    if normalized_type is None:
        return {}

    normalized_keys: list[str] = []
    seen_keys: set[str] = set()
    for target_id in target_ids:
        normalized_key = normalize_media_target_key(normalized_type, target_id)
        if normalized_key is None or normalized_key in seen_keys:
            continue
        seen_keys.add(normalized_key)
        normalized_keys.append(normalized_key)

    if not normalized_keys:
        return {}

    effective_limit = max(1, int(limit_per_target or 6))
    viewer_id = int(getattr(viewer, "pk", 0) or 0) if bool(getattr(viewer, "is_authenticated", False)) else 0

    rows = MediaAttachment.objects.select_related("asset", "asset__owner").filter(
        target_type=normalized_type,
        target_key__in=normalized_keys,
    ).order_by("target_key", "-created_at", "-pk")

    result: dict[str, list[MediaAttachmentData]] = {key: [] for key in normalized_keys}
    for row in rows:
        bucket = result.get(row.target_key)
        if bucket is None:
            continue
        if len(bucket) >= effective_limit:
            continue
        bucket.append(row.asset.to_attachment_data(attachment=row, viewer_id=viewer_id))

    return result


def build_media_payload_for_target(
    *,
    target_type: object,
    target_id: object,
    viewer: object,
    limit: int = 24,
) -> MediaTargetPayload:
    resolved_target = resolve_media_target(target_type, target_id)
    if resolved_target is None:
        return {
            "attachments": [],
            "mode": "invalid-target",
            "reason": "Media is unavailable because this target could not be resolved.",
            "target_type": str(target_type or "").strip().lower(),
            "target_key": str(target_id or "").strip().lower(),
            "target_label": "Unavailable target",
            "target_url": "#",
            "can_upload": False,
        }

    effective_limit = max(1, int(limit or 24))
    viewer_is_member = bool(getattr(viewer, "is_authenticated", False))
    viewer_id = int(getattr(viewer, "pk", 0) or 0) if viewer_is_member else 0

    rows = MediaAttachment.objects.select_related("asset", "asset__owner").filter(
        target_type=resolved_target.target_type,
        target_key=resolved_target.target_key,
    ).order_by("-created_at", "-pk")[:effective_limit]
    attachments = [row.asset.to_attachment_data(attachment=row, viewer_id=viewer_id) for row in rows]

    reason = "Media attachments are ordered from newest to oldest."
    if not attachments:
        reason = "No media yet. Add a few photos or clips to help members evaluate this page quickly."

    payload: MediaTargetPayload = {
        "attachments": attachments,
        "mode": "member-target-media" if viewer_is_member else "guest-target-media",
        "reason": reason,
        "target_type": str(resolved_target.target_type),
        "target_key": resolved_target.target_key,
        "target_label": resolved_target.target_label,
        "target_url": resolved_target.target_url,
        "can_upload": viewer_id > 0 and viewer_id == resolved_target.owner_id,
    }
    return payload


def submit_media_upload(
    *,
    member: object,
    target_type: object,
    target_id: object,
    uploaded_file: UploadedFile | None,
    caption: object = "",
) -> tuple[MediaAsset | None, MediaAttachment | None, MediaUploadOutcome, MediaTargetResolution | None]:
    if not bool(getattr(member, "is_authenticated", False)):
        return None, None, "member-required", None

    member_id = int(getattr(member, "pk", 0) or 0)
    if member_id <= 0:
        return None, None, "invalid-member", None

    if uploaded_file is None:
        return None, None, "missing-file", None

    resolved_target = resolve_media_target(target_type, target_id)
    if resolved_target is None:
        if normalize_media_target_type(target_type) is None:
            return None, None, "invalid-target-type", None
        return None, None, "target-not-found", None

    if resolved_target.owner_id != member_id:
        return None, None, "permission-denied", resolved_target

    size_bytes = int(getattr(uploaded_file, "size", 0) or 0)
    if size_bytes <= 0:
        return None, None, "empty-file", resolved_target

    kind, normalized_content_type, classify_error = _classify_upload(uploaded_file)
    if classify_error is not None or kind is None:
        return None, None, "invalid-content-type", resolved_target

    if size_bytes > _max_bytes_for_kind(kind):
        return None, None, "file-too-large", resolved_target

    cleaned_caption = _clean_text(caption)
    if len(cleaned_caption) > MediaAsset.CAPTION_MAX_LENGTH:
        return None, None, "too-long-caption", resolved_target

    image_width: int | None = None
    image_height: int | None = None
    if kind == "image":
        image_width, image_height = _extract_image_dimensions(uploaded_file)
        if image_width is None or image_height is None:
            return None, None, "invalid-image", resolved_target

    checksum_sha256 = _sha256_for_uploaded_file(uploaded_file)

    existing_attachment = MediaAttachment.objects.select_related("asset", "asset__owner").filter(
        target_type=resolved_target.target_type,
        target_key=resolved_target.target_key,
        asset__owner_id=member_id,
        asset__checksum_sha256=checksum_sha256,
    ).order_by("-created_at", "-pk").first()
    if existing_attachment is not None:
        changed_fields: list[str] = []
        if existing_attachment.target_label != resolved_target.target_label:
            existing_attachment.target_label = resolved_target.target_label
            changed_fields.append("target_label")
        if existing_attachment.target_url != resolved_target.target_url:
            existing_attachment.target_url = resolved_target.target_url
            changed_fields.append("target_url")
        if changed_fields:
            changed_fields.append("updated_at")
            existing_attachment.save(update_fields=changed_fields)
        return existing_attachment.asset, existing_attachment, "already-attached", resolved_target

    reusable_asset = MediaAsset.objects.filter(
        owner_id=member_id,
        checksum_sha256=checksum_sha256,
        size_bytes=size_bytes,
        kind=kind,
    ).order_by("-created_at", "-pk").first()
    if reusable_asset is not None:
        attachment, created = MediaAttachment.objects.get_or_create(
            asset=reusable_asset,
            target_type=resolved_target.target_type,
            target_key=resolved_target.target_key,
            defaults={
                "target_label": resolved_target.target_label,
                "target_url": resolved_target.target_url,
            },
        )
        if not created:
            return reusable_asset, attachment, "already-attached", resolved_target
        return reusable_asset, attachment, "attached-existing", resolved_target

    asset = MediaAsset(
        owner=cast(Any, member),
        file=uploaded_file,
        kind=kind,
        original_name=Path(str(getattr(uploaded_file, "name", "upload.bin") or "upload.bin")).name,
        content_type=normalized_content_type,
        size_bytes=size_bytes,
        checksum_sha256=checksum_sha256,
        width_px=image_width,
        height_px=image_height,
        caption=cleaned_caption,
    )
    asset.full_clean()
    asset.save()

    attachment = MediaAttachment(
        asset=asset,
        target_type=resolved_target.target_type,
        target_key=resolved_target.target_key,
        target_label=resolved_target.target_label,
        target_url=resolved_target.target_url,
    )
    attachment.full_clean()
    attachment.save()

    return asset, attachment, "created", resolved_target


def remove_media_attachment(
    *,
    member: object,
    attachment_id: object,
) -> tuple[MediaAttachment | None, MediaDeleteOutcome]:
    if not bool(getattr(member, "is_authenticated", False)):
        return None, "member-required"

    member_id = int(getattr(member, "pk", 0) or 0)
    if member_id <= 0:
        return None, "invalid-member"

    attachment_pk_text = str(attachment_id or "").strip()
    if not attachment_pk_text.isdigit():
        return None, "not-found"

    attachment = MediaAttachment.objects.select_related("asset", "asset__owner").filter(
        pk=int(attachment_pk_text)
    ).first()
    if attachment is None:
        return None, "not-found"

    asset = attachment.asset
    if int(getattr(asset, "owner_id", 0) or 0) != member_id:
        return attachment, "permission-denied"

    attachment.delete()

    remaining_attachments_exist = MediaAttachment.objects.filter(asset=asset).exists()
    if remaining_attachments_exist:
        return attachment, "deleted-attachment"

    try:
        if asset.file:
            asset.file.delete(save=False)
    except Exception:
        pass

    asset.delete()
    return attachment, "deleted-attachment-and-asset"
