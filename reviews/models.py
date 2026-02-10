from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal, TypedDict, cast

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Avg, Count, Q
from django.db.models.constraints import BaseConstraint

from feed.models import get_blog_by_slug, get_demo_blogs, get_trip_by_id

ReviewTargetType = Literal["trip", "blog"]
ReviewSubmitOutcome = Literal[
    "member-required",
    "invalid-member",
    "invalid-target-type",
    "target-not-found",
    "invalid-rating",
    "empty-body",
    "too-long-body",
    "too-long-headline",
    "created",
    "updated",
]

ALLOWED_REVIEW_TARGET_TYPES: Final[set[str]] = {"trip", "blog"}


class ReviewData(TypedDict):
    id: int
    author_username: str
    rating: int
    headline: str
    body: str
    created_at: datetime
    updated_at: datetime
    is_mine: bool


class RatingBucketData(TypedDict):
    rating: int
    count: int


class ReviewTargetPayload(TypedDict):
    reviews: list[ReviewData]
    rating_buckets: list[RatingBucketData]
    mode: str
    reason: str
    target_type: str
    target_key: str
    target_label: str
    target_url: str
    review_count: int
    average_rating: float
    can_review: bool
    viewer_review: ReviewData | None


@dataclass(frozen=True)
class ReviewTargetResolution:
    target_type: ReviewTargetType
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
    # Keep user text normalized so equality checks and idempotent seeds are stable.
    return " ".join(str(value or "").strip().split())


def parse_review_rating(raw_rating: object) -> int | None:
    raw_text = str(raw_rating or "").strip()
    if not raw_text:
        return None

    if raw_text.startswith("+"):
        raw_text = raw_text[1:]
    if not raw_text.isdigit():
        return None

    rating = int(raw_text)
    if rating < Review.RATING_MIN or rating > Review.RATING_MAX:
        return None
    return rating


def normalize_review_target_type(raw_target_type: object) -> ReviewTargetType | None:
    normalized = str(raw_target_type or "").strip().lower()
    if normalized in ALLOWED_REVIEW_TARGET_TYPES:
        return cast(ReviewTargetType, normalized)
    return None


def normalize_review_target_key(target_type: str, raw_target_id: object) -> str | None:
    normalized_type = normalize_review_target_type(target_type)
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


def resolve_review_target(
    target_type: str,
    raw_target_id: object,
) -> ReviewTargetResolution | None:
    normalized_type = normalize_review_target_type(target_type)
    if normalized_type is None:
        return None

    normalized_key = normalize_review_target_key(normalized_type, raw_target_id)
    if normalized_key is None:
        return None

    if normalized_type == "trip":
        trip = _trip_from_key(normalized_key)
        if trip is not None:
            trip_id = int(getattr(trip, "pk", 0) or 0)
            if trip_id <= 0:
                return None

            trip_title = str(getattr(trip, "title", "") or "").strip() or f"Trip #{trip_id}"
            return ReviewTargetResolution(
                target_type="trip",
                target_key=str(trip_id),
                target_label=trip_title,
                target_url=_absolute_url(trip, fallback=f"/trips/{trip_id}/"),
            )

        demo_trip = get_trip_by_id(int(normalized_key))
        if demo_trip is None:
            return None

        demo_trip_id = int(demo_trip.get("id", 0) or 0)
        if demo_trip_id <= 0:
            return None

        demo_trip_title = str(demo_trip.get("title", "") or "").strip() or f"Trip #{demo_trip_id}"
        return ReviewTargetResolution(
            target_type="trip",
            target_key=str(demo_trip_id),
            target_label=demo_trip_title,
            target_url=str(demo_trip.get("url", "") or "").strip() or f"/trips/{demo_trip_id}/",
        )

    blog = _blog_from_key(normalized_key)
    if blog is not None:
        slug = str(getattr(blog, "slug", "") or "").strip().lower()
        if not slug:
            return None

        blog_title = str(getattr(blog, "title", "") or "").strip() or slug.replace("-", " ").title()
        return ReviewTargetResolution(
            target_type="blog",
            target_key=slug,
            target_label=blog_title,
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

    demo_blog_title = str(demo_blog.get("title", "") or "").strip() or demo_slug.replace("-", " ").title()
    return ReviewTargetResolution(
        target_type="blog",
        target_key=demo_slug,
        target_label=demo_blog_title,
        target_url=str(demo_blog.get("url", "") or "").strip() or f"/blogs/{demo_slug}/",
    )


class Review(models.Model):
    """
    Member review row for trip and blog targets.

    One review per `(author, target_type, target_key)` keeps writes idempotent
    and allows simple update semantics for repeated submissions.
    """

    TARGET_TRIP: Final[str] = "trip"
    TARGET_BLOG: Final[str] = "blog"
    TARGET_TYPE_CHOICES: Final[tuple[tuple[str, str], ...]] = (
        (TARGET_TRIP, "Trip"),
        (TARGET_BLOG, "Blog"),
    )
    RATING_MIN: Final[int] = 1
    RATING_MAX: Final[int] = 5
    HEADLINE_MAX_LENGTH: Final[int] = 160
    BODY_MAX_LENGTH: Final[int] = 4_000

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="authored_reviews",
    )
    target_type = models.CharField(max_length=12, choices=TARGET_TYPE_CHOICES)
    target_key = models.CharField(max_length=191)
    target_label = models.CharField(max_length=255, blank=True)
    target_url = models.CharField(max_length=255, blank=True)
    rating = models.PositiveSmallIntegerField(default=5)
    headline = models.CharField(max_length=HEADLINE_MAX_LENGTH, blank=True)
    body = models.CharField(max_length=BODY_MAX_LENGTH)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints: list[BaseConstraint] = [
            cast(
                BaseConstraint,
                models.UniqueConstraint(
                    fields=("author", "target_type", "target_key"),
                    name="reviews_unique_author_target",
                ),
            ),
            cast(
                BaseConstraint,
                models.CheckConstraint(
                    condition=Q(rating__gte=1) & Q(rating__lte=5),
                    name="reviews_rating_between_1_5",
                ),
            ),
        ]
        indexes = [
            models.Index(fields=("target_type", "target_key", "created_at"), name="reviews_target_created_idx"),
            models.Index(fields=("author", "created_at"), name="reviews_author_created_idx"),
        ]

    def __str__(self) -> str:
        author_username = str(getattr(self.author, "username", "") or "").strip()
        return (
            f"Review #{self.pk or 'new'} "
            f"by @{author_username} for {self.target_type}:{self.target_key} ({self.rating}/5)"
        )

    def clean(self) -> None:
        super().clean()

        normalized_type = normalize_review_target_type(self.target_type)
        if normalized_type is None:
            raise ValidationError({"target_type": "Unsupported review target type."})

        normalized_key = normalize_review_target_key(normalized_type, self.target_key)
        if normalized_key is None:
            raise ValidationError({"target_key": "Invalid review target identifier."})

        rating_value = int(self.rating or 0)
        if rating_value < self.RATING_MIN or rating_value > self.RATING_MAX:
            raise ValidationError(
                {"rating": f"Rating must be between {self.RATING_MIN} and {self.RATING_MAX}."}
            )

        cleaned_headline = _clean_text(self.headline)
        cleaned_body = _clean_text(self.body)
        if len(cleaned_headline) > self.HEADLINE_MAX_LENGTH:
            raise ValidationError(
                {"headline": f"Headline must be {self.HEADLINE_MAX_LENGTH} characters or fewer."}
            )
        if not cleaned_body:
            raise ValidationError({"body": "Review text cannot be empty."})
        if len(cleaned_body) > self.BODY_MAX_LENGTH:
            raise ValidationError({"body": f"Review text must be {self.BODY_MAX_LENGTH} characters or fewer."})

        self.target_type = normalized_type
        self.target_key = normalized_key
        self.rating = rating_value
        self.headline = cleaned_headline
        self.body = cleaned_body

    def to_review_data(self, *, viewer_id: int) -> ReviewData:
        author_username = str(getattr(self.author, "username", "") or "").strip()
        return {
            "id": int(self.pk or 0),
            "author_username": author_username,
            "rating": int(self.rating or 0),
            "headline": str(self.headline or "").strip(),
            "body": str(self.body or "").strip(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_mine": int(getattr(self, "author_id", 0) or 0) == int(viewer_id),
        }


def _sync_target_review_counts(target: ReviewTargetResolution) -> None:
    """
    Keep denormalized review counters aligned for live target rows.

    Today only `blogs.Blog.reviews_count` exists, but this hook keeps the write
    path ready for future per-target counters.
    """

    if target.target_type != "blog":
        return

    blog_row = _blog_from_key(target.target_key)
    if blog_row is None or not hasattr(blog_row, "reviews_count"):
        return

    target_review_count = Review.objects.filter(
        target_type=target.target_type,
        target_key=target.target_key,
    ).count()
    current_count = int(getattr(blog_row, "reviews_count", 0) or 0)

    if current_count == target_review_count:
        return

    setattr(blog_row, "reviews_count", target_review_count)
    update_fields = ["reviews_count"]
    if hasattr(blog_row, "updated_at"):
        update_fields.append("updated_at")
    blog_row.save(update_fields=update_fields)


def submit_review(
    *,
    member: object,
    target_type: object,
    target_id: object,
    rating: object,
    headline: object = "",
    body: object,
) -> tuple[Review | None, ReviewSubmitOutcome, ReviewTargetResolution | None]:
    if not bool(getattr(member, "is_authenticated", False)):
        return None, "member-required", None

    member_id = int(getattr(member, "pk", 0) or 0)
    if member_id <= 0:
        return None, "invalid-member", None

    resolved_target = resolve_review_target(str(target_type or ""), target_id)
    if resolved_target is None:
        if normalize_review_target_type(target_type) is None:
            return None, "invalid-target-type", None
        return None, "target-not-found", None

    parsed_rating = parse_review_rating(rating)
    if parsed_rating is None:
        return None, "invalid-rating", resolved_target

    cleaned_headline = _clean_text(headline)
    if len(cleaned_headline) > Review.HEADLINE_MAX_LENGTH:
        return None, "too-long-headline", resolved_target

    cleaned_body = _clean_text(body)
    if not cleaned_body:
        return None, "empty-body", resolved_target
    if len(cleaned_body) > Review.BODY_MAX_LENGTH:
        return None, "too-long-body", resolved_target

    review_row, created = Review.objects.get_or_create(
        author=cast(Any, member),
        target_type=resolved_target.target_type,
        target_key=resolved_target.target_key,
        defaults={
            "target_label": resolved_target.target_label,
            "target_url": resolved_target.target_url,
            "rating": parsed_rating,
            "headline": cleaned_headline,
            "body": cleaned_body,
        },
    )

    if created:
        _sync_target_review_counts(resolved_target)
        return review_row, "created", resolved_target

    changed_fields: list[str] = []
    if review_row.target_label != resolved_target.target_label:
        review_row.target_label = resolved_target.target_label
        changed_fields.append("target_label")
    if review_row.target_url != resolved_target.target_url:
        review_row.target_url = resolved_target.target_url
        changed_fields.append("target_url")
    if int(review_row.rating or 0) != parsed_rating:
        review_row.rating = parsed_rating
        changed_fields.append("rating")
    if review_row.headline != cleaned_headline:
        review_row.headline = cleaned_headline
        changed_fields.append("headline")
    if review_row.body != cleaned_body:
        review_row.body = cleaned_body
        changed_fields.append("body")

    if changed_fields:
        changed_fields.append("updated_at")
        review_row.save(update_fields=changed_fields)

    _sync_target_review_counts(resolved_target)
    return review_row, "updated", resolved_target


def build_reviews_payload_for_target(
    *,
    target_type: object,
    target_id: object,
    viewer: object,
    limit: int = 120,
) -> ReviewTargetPayload:
    resolved_target = resolve_review_target(str(target_type or ""), target_id)
    if resolved_target is None:
        return {
            "reviews": [],
            "rating_buckets": [{"rating": rating, "count": 0} for rating in range(5, 0, -1)],
            "mode": "invalid-target",
            "reason": "Reviews are unavailable because this target could not be resolved.",
            "target_type": str(target_type or "").strip().lower(),
            "target_key": str(target_id or "").strip().lower(),
            "target_label": "Unavailable",
            "target_url": "#",
            "review_count": 0,
            "average_rating": 0.0,
            "can_review": bool(getattr(viewer, "is_authenticated", False)),
            "viewer_review": None,
        }

    effective_limit = max(1, int(limit or 120))
    base_queryset = Review.objects.select_related("author").filter(
        target_type=resolved_target.target_type,
        target_key=resolved_target.target_key,
    )
    review_rows = list(base_queryset.order_by("-created_at", "-pk")[:effective_limit])
    review_count = int(base_queryset.count())

    aggregate_result = base_queryset.aggregate(average=Avg("rating"))
    average_rating = float(aggregate_result.get("average") or 0.0)
    average_rating = round(average_rating, 2)

    rating_counts = {
        int(item["rating"]): int(item["count"])
        for item in base_queryset.values("rating").annotate(count=Count("id"))
    }
    rating_buckets: list[RatingBucketData] = [
        {"rating": rating_value, "count": rating_counts.get(rating_value, 0)}
        for rating_value in range(5, 0, -1)
    ]

    viewer_is_member = bool(getattr(viewer, "is_authenticated", False))
    viewer_id = int(getattr(viewer, "pk", 0) or 0) if viewer_is_member else 0
    reviews_data = [row.to_review_data(viewer_id=viewer_id) for row in review_rows]
    viewer_review = next((row for row in reviews_data if bool(row.get("is_mine"))), None)

    reason = "Reviews are ordered from newest to oldest."
    if review_count == 0:
        reason = "No reviews yet. Members can add the first review."

    return {
        "reviews": reviews_data,
        "rating_buckets": rating_buckets,
        "mode": "member-target-reviews" if viewer_is_member else "guest-target-reviews",
        "reason": reason,
        "target_type": resolved_target.target_type,
        "target_key": resolved_target.target_key,
        "target_label": resolved_target.target_label,
        "target_url": resolved_target.target_url,
        "review_count": review_count,
        "average_rating": average_rating,
        "can_review": viewer_is_member,
        "viewer_review": viewer_review,
    }
