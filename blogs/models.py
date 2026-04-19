from __future__ import annotations

from hashlib import md5
from typing import Any, TypedDict, cast

from django.conf import settings
from django.db import models

from feed.models import BlogData, MemberFeedPreference, get_blog_by_slug, get_demo_blogs
from tapne.features import _demo_qs_filter, demo_catalog_enabled


class BlogListPayload(TypedDict):
    blogs: list[BlogData]
    mode: str
    reason: str
    source: str


class BlogDetailPayload(TypedDict):
    blog: BlogData
    mode: str
    reason: str
    source: str
    can_manage_blog: bool


class Blog(models.Model):
    """
    Core blog record used by list/detail/CRUD flows.

    The schema intentionally mirrors the README contract and feed/search payload
    shape so ranking and discovery can share one representation.
    """

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="authored_blogs",
    )
    slug = models.SlugField(max_length=180, unique=True)
    title = models.CharField(max_length=180)
    excerpt = models.CharField(max_length=280, blank=True)
    body = models.TextField(blank=True)
    cover_image_url = models.TextField(blank=True, default="")
    location = models.CharField(max_length=180, blank=True, default="")
    tags = cast(list[str], models.JSONField(default=list, blank=True))
    reads = models.PositiveIntegerField(default=0)
    reviews_count = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True, db_index=True)
    is_demo = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=("author", "created_at"), name="blog_author_created_idx"),
            models.Index(fields=("is_published", "created_at"), name="blog_pub_created_idx"),
            models.Index(fields=("reads", "id"), name="blog_reads_rank_idx"),
        ]

    def __str__(self) -> str:
        return f"Blog #{self.pk or 'new'}: {self.title}"

    def get_absolute_url(self) -> str:
        return f"/blogs/{self.slug}/"

    def _default_cover_image_url(self) -> str:
        cover_pool: tuple[str, ...] = (
            "https://images.unsplash.com/photo-1512343879784-a960bf40e7f2?w=900&q=80",
            "https://images.unsplash.com/photo-1626621341517-bbf3d9990a23?w=900&q=80",
            "https://images.unsplash.com/photo-1537996194471-e657df975ab4?w=900&q=80",
            "https://images.unsplash.com/photo-1477587458883-47145ed94245?w=900&q=80",
            "https://images.unsplash.com/photo-1602216056096-3b40cc0c9944?w=900&q=80",
            "https://images.unsplash.com/photo-1626014303715-48c7b1a7a814?w=900&q=80",
        )
        if not cover_pool:
            return ""
        slug_key = str(self.slug or self.pk or "tapne-blog")
        index = int(md5(slug_key.encode("utf-8")).hexdigest(), 16) % len(cover_pool)
        return cover_pool[index]

    def to_blog_data(self) -> BlogData:
        cover_image_url = str(self.cover_image_url or "").strip() or self._default_cover_image_url()
        tags = [str(tag or "").strip() for tag in self.tags if str(tag or "").strip()]
        return {
            "id": int(self.pk or 0),
            "slug": self.slug,
            "title": self.title,
            "excerpt": self.excerpt,
            "short_description": self.excerpt,
            "summary": self.excerpt,
            "author_username": str(getattr(self.author, "username", "") or "").strip(),
            "reads": int(self.reads or 0),
            "reviews_count": int(self.reviews_count or 0),
            "url": self.get_absolute_url(),
            "body": self.body,
            "cover_image_url": cover_image_url,
            "location": str(self.location or "").strip(),
            "tags": tags,
            "published_label": self.created_at.strftime("%b %d, %Y"),
        }


def _as_blog_data_copy(item: BlogData) -> BlogData:
    return cast(BlogData, dict(item))


def _reads_score(blog: BlogData) -> int:
    try:
        return int(blog.get("reads", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _default_interest_keywords_for_username(username: str) -> set[str]:
    lowered = username.strip().lower()
    if lowered.startswith("m"):
        return {"food", "city", "guide"}
    if lowered.startswith("a"):
        return {"mountain", "trek", "camp"}
    if lowered.startswith("s"):
        return {"desert", "market", "route"}
    return {"blog", "guide"}


def _member_ranking_sets(user: object) -> tuple[set[str], set[str], bool]:
    typed_user = cast(Any, user)
    username = str(getattr(typed_user, "username", "") or "").strip()

    if not bool(getattr(typed_user, "is_authenticated", False)):
        return set(), set(), False

    try:
        preference = cast(MemberFeedPreference, typed_user.feed_preference)
        raw_followed = getattr(preference, "followed_usernames", [])
        raw_interests = getattr(preference, "interest_keywords", [])

        followed_usernames = {
            str(item or "").strip().lower()
            for item in raw_followed
            if str(item or "").strip()
        }
        interest_keywords = {
            str(item or "").strip().lower()
            for item in raw_interests
            if str(item or "").strip()
        }
        if not interest_keywords:
            interest_keywords = _default_interest_keywords_for_username(username)
        return followed_usernames, interest_keywords, True
    except (MemberFeedPreference.DoesNotExist, AttributeError):
        return set(), _default_interest_keywords_for_username(username), False


def _content_matches_keywords(keywords: set[str], *values: object) -> bool:
    if not keywords:
        return False
    haystack = " ".join(str(value or "").lower() for value in values)
    return any(keyword in haystack for keyword in keywords)


def _rank_for_guest(blogs: list[BlogData]) -> list[BlogData]:
    return sorted(
        blogs,
        key=lambda blog: (
            _reads_score(blog),
            str(blog.get("title", "")).lower(),
        ),
        reverse=True,
    )


def _rank_for_member(
    blogs: list[BlogData],
    *,
    followed_usernames: set[str],
    interest_keywords: set[str],
) -> list[BlogData]:
    def blog_rank_score(blog: BlogData) -> int:
        score = _reads_score(blog)
        author_username = str(blog.get("author_username", "")).strip().lower()

        if author_username and author_username in followed_usernames:
            score += 10_000

        if _content_matches_keywords(
            interest_keywords,
            blog.get("title"),
            blog.get("excerpt"),
            blog.get("summary"),
            blog.get("body"),
        ):
            score += 700

        return score

    return sorted(
        blogs,
        key=lambda blog: (
            blog_rank_score(blog),
            str(blog.get("title", "")).lower(),
        ),
        reverse=True,
    )


def _live_blog_rows() -> list[Blog]:
    return list(
        Blog.objects.select_related("author")
        .filter(is_published=True, **_demo_qs_filter())
        .order_by("-created_at", "-pk")
    )


def build_blog_list_payload_for_user(user: object, limit: int = 24) -> BlogListPayload:
    effective_limit = max(1, int(limit or 24))

    live_rows = _live_blog_rows()
    source = "live-db"
    candidate_blogs = [blog.to_blog_data() for blog in live_rows]

    if not candidate_blogs and demo_catalog_enabled():
        source = "demo-fallback"
        candidate_blogs = [_as_blog_data_copy(item) for item in get_demo_blogs()]

    if bool(getattr(user, "is_authenticated", False)):
        followed_usernames, interest_keywords, has_saved_preference = _member_ranking_sets(user)
        ranked_blogs = _rank_for_member(
            candidate_blogs,
            followed_usernames=followed_usernames,
            interest_keywords=interest_keywords,
        )

        reason = "Blogs ranked using followed authors and like-minded topic boosts."
        if not has_saved_preference:
            reason = "Blogs ranked with fallback member interests until preferences are saved."

        mode = "member-like-minded-live" if source == "live-db" else "member-like-minded-demo"
        return {
            "blogs": ranked_blogs[:effective_limit],
            "mode": mode,
            "reason": reason,
            "source": source,
        }

    ranked_blogs = _rank_for_guest(candidate_blogs)
    mode = "guest-most-read-live" if source == "live-db" else "guest-most-read-demo"
    reason = "Blogs ranked by global readership demand for guests."
    return {
        "blogs": ranked_blogs[:effective_limit],
        "mode": mode,
        "reason": reason,
        "source": source,
    }


def build_blog_detail_payload_for_user(user: object, slug: str) -> BlogDetailPayload:
    viewer_is_member = bool(getattr(user, "is_authenticated", False))
    viewer_id = int(getattr(user, "pk", 0) or 0)

    live_row = Blog.objects.select_related("author").filter(slug=slug).first()
    live_row_author_id = int(getattr(live_row, "author_id", 0) or 0) if live_row is not None else 0

    blog_data: BlogData
    source: str
    can_manage_blog = False

    if live_row is not None and (
        live_row.is_published or (viewer_is_member and live_row_author_id == viewer_id)
    ):
        blog_data = live_row.to_blog_data()
        source = "live-db"
        can_manage_blog = bool(viewer_is_member and live_row_author_id == viewer_id)
    else:
        demo_blog = get_blog_by_slug(slug) if demo_catalog_enabled() else None
        if demo_blog is not None:
            blog_data = _as_blog_data_copy(demo_blog)
            source = "demo-fallback"
        else:
            blog_data = {
                "id": 0,
                "slug": slug,
                "title": slug.replace("-", " ").title() or "Blog not found",
                "excerpt": "Blog record not found.",
                "summary": "Blog record not found.",
                "body": "Blog record is not available in live storage or demo fallback data.",
                "reads": 0,
                "reviews_count": 0,
                "url": f"/blogs/{slug}/",
            }
            source = "synthetic-fallback"

    if viewer_is_member:
        mode = "member-full"
        reason = "Members can read and interact with full blog content."
    else:
        mode = "guest-full"
        reason = "Guests can read full blog content, but actions require login."

    return {
        "blog": blog_data,
        "mode": mode,
        "reason": reason,
        "source": source,
        "can_manage_blog": can_manage_blog,
    }
