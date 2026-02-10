from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandParser
from django.utils import timezone

from enrollment.models import EnrollmentRequest
from interactions.models import Comment, resolve_comment_target
from reviews.models import submit_review
from social.models import Bookmark, FollowRelation, resolve_bookmark_target
from trips.models import Trip

UserModel = get_user_model()


@dataclass(frozen=True)
class FollowSeed:
    follower_username: str
    following_username: str


@dataclass(frozen=True)
class EnrollmentSeed:
    requester_username: str
    trip_id: int
    status: str
    message: str


@dataclass(frozen=True)
class CommentSeed:
    key: str
    author_username: str
    target_type: str
    target_id: str
    text: str


@dataclass(frozen=True)
class ReplySeed:
    author_username: str
    parent_key: str
    text: str


@dataclass(frozen=True)
class BookmarkSeed:
    member_username: str
    target_type: str
    target_id: str


@dataclass(frozen=True)
class ReviewSeed:
    member_username: str
    target_type: str
    target_id: str
    rating: int
    headline: str
    body: str


DEMO_FOLLOW_SEEDS: tuple[FollowSeed, ...] = (
    FollowSeed(follower_username="arun", following_username="mei"),
    FollowSeed(follower_username="sahar", following_username="mei"),
    FollowSeed(follower_username="nora", following_username="mei"),
)

DEMO_ENROLLMENT_SEEDS: tuple[EnrollmentSeed, ...] = (
    EnrollmentSeed(
        requester_username="mei",
        trip_id=102,
        status=EnrollmentRequest.STATUS_APPROVED,
        message="Requesting approval for this route.",
    ),
    EnrollmentSeed(
        requester_username="mei",
        trip_id=103,
        status=EnrollmentRequest.STATUS_DENIED,
        message="Happy with either schedule if a slot opens.",
    ),
)

DEMO_COMMENT_SEEDS: tuple[CommentSeed, ...] = (
    CommentSeed(
        key="incoming-mei-trip",
        author_username="arun",
        target_type="trip",
        target_id="101",
        text="This itinerary is clear and easy to follow.",
    ),
    CommentSeed(
        key="mei-comment-for-reply",
        author_username="mei",
        target_type="trip",
        target_id="102",
        text="Leaving this note so collaborators can reply with handoff tips.",
    ),
)

DEMO_REPLY_SEEDS: tuple[ReplySeed, ...] = (
    ReplySeed(
        author_username="sahar",
        parent_key="mei-comment-for-reply",
        text="Adding a handoff checklist from my last trip cycle.",
    ),
)

DEMO_BOOKMARK_SEEDS: tuple[BookmarkSeed, ...] = (
    BookmarkSeed(member_username="arun", target_type="user", target_id="mei"),
    BookmarkSeed(member_username="sahar", target_type="trip", target_id="101"),
    BookmarkSeed(member_username="arun", target_type="blog", target_id="packing-for-swing-weather"),
)

DEMO_REVIEW_SEEDS: tuple[ReviewSeed, ...] = (
    ReviewSeed(
        member_username="arun",
        target_type="trip",
        target_id="101",
        rating=5,
        headline="Solid host pacing",
        body="Clear checkpoints and practical pacing for mixed experience members.",
    ),
    ReviewSeed(
        member_username="sahar",
        target_type="blog",
        target_id="packing-for-swing-weather",
        rating=4,
        headline="Useful checklist",
        body="The packing framework is easy to reuse and keeps pre-trip prep focused.",
    ),
)


class Command(BaseCommand):
    help = "Create or refresh demo rows that power member activity feeds."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--create-missing-members",
            action="store_true",
            help="Create missing seed members before writing activity seed rows.",
        )
        parser.add_argument(
            "--demo-password",
            default="TapneDemoPass!123",
            help="Password used only when --create-missing-members creates users.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print detailed progress for each activity seed operation.",
        )

    def _vprint(self, verbose_enabled: bool, message: str) -> None:
        if verbose_enabled:
            self.stdout.write(f"[activity][verbose] {message}")

    def _resolve_member(
        self,
        *,
        username: str,
        create_missing_members: bool,
        demo_password: str,
        verbose_enabled: bool,
    ) -> tuple[Any | None, bool]:
        member = cast(Any | None, UserModel.objects.filter(username__iexact=username).first())
        if member is not None:
            if member.username != username:
                member.username = username
                member.save(update_fields=["username"])
                self._vprint(verbose_enabled, f"Normalized username casing for @{username}")
            return member, False

        if not create_missing_members:
            self._vprint(
                verbose_enabled,
                (
                    f"Skipping @{username}; user does not exist and "
                    "--create-missing-members is disabled."
                ),
            )
            return None, False

        member = UserModel.objects.create_user(
            username=username,
            email=f"{username}@tapne.local",
            password=demo_password,
        )
        self._vprint(verbose_enabled, f"Created missing member @{username}")
        return member, True

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        verbose_enabled = bool(options.get("verbose"))
        create_missing_members = bool(options.get("create_missing_members"))
        demo_password = str(options.get("demo_password") or "TapneDemoPass!123")
        now = timezone.now()

        self.stdout.write("Bootstrapping activity event source records...")
        self._vprint(verbose_enabled, f"create_missing_members={create_missing_members}")

        created_members_count = 0
        created_follows_count = 0
        skipped_follows_count = 0
        created_enrollment_count = 0
        updated_enrollment_count = 0
        skipped_enrollment_count = 0
        created_comment_count = 0
        updated_comment_count = 0
        created_reply_count = 0
        updated_reply_count = 0
        skipped_comment_ops_count = 0
        created_bookmark_count = 0
        updated_bookmark_count = 0
        skipped_bookmark_count = 0
        created_review_count = 0
        updated_review_count = 0
        skipped_review_count = 0

        member_cache: dict[str, Any | None] = {}

        def get_member(username: str) -> Any | None:
            nonlocal created_members_count
            cache_key = username.lower()
            if cache_key in member_cache:
                return member_cache[cache_key]

            member, created = self._resolve_member(
                username=username,
                create_missing_members=create_missing_members,
                demo_password=demo_password,
                verbose_enabled=verbose_enabled,
            )
            if created:
                created_members_count += 1
            member_cache[cache_key] = member
            return member

        for seed in DEMO_FOLLOW_SEEDS:
            follower = get_member(seed.follower_username)
            following = get_member(seed.following_username)
            if follower is None or following is None:
                skipped_follows_count += 1
                continue

            if int(getattr(follower, "pk", 0) or 0) == int(getattr(following, "pk", 0) or 0):
                skipped_follows_count += 1
                self._vprint(
                    verbose_enabled,
                    f"Skipping invalid self-follow seed @{seed.follower_username}",
                )
                continue

            relation, created = FollowRelation.objects.get_or_create(
                follower=follower,
                following=following,
            )
            if created:
                created_follows_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        f"Created follow relation @{seed.follower_username} -> "
                        f"@{seed.following_username} (id={relation.pk})"
                    ),
                )
            else:
                self._vprint(
                    verbose_enabled,
                    (
                        f"Follow relation already exists @{seed.follower_username} -> "
                        f"@{seed.following_username}"
                    ),
                )

        for seed in DEMO_ENROLLMENT_SEEDS:
            requester = get_member(seed.requester_username)
            if requester is None:
                skipped_enrollment_count += 1
                continue

            trip = Trip.objects.select_related("host").filter(pk=seed.trip_id).first()
            if trip is None:
                skipped_enrollment_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Skipping enrollment seed requester=@{requester}; "
                        "trip id={trip_id} not found."
                    ).format(
                        requester=seed.requester_username,
                        trip_id=seed.trip_id,
                    ),
                )
                continue

            if int(getattr(trip, "host_id", 0) or 0) == int(getattr(requester, "pk", 0) or 0):
                skipped_enrollment_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Skipping enrollment seed requester=@{requester}; "
                        "requester is host for trip id={trip_id}."
                    ).format(
                        requester=seed.requester_username,
                        trip_id=seed.trip_id,
                    ),
                )
                continue

            reviewed_by = trip.host if seed.status in {
                EnrollmentRequest.STATUS_APPROVED,
                EnrollmentRequest.STATUS_DENIED,
            } else None
            reviewed_at = now if reviewed_by is not None else None

            request_row, created = EnrollmentRequest.objects.update_or_create(
                trip=trip,
                requester=requester,
                defaults={
                    "message": seed.message,
                    "status": seed.status,
                    "reviewed_by": reviewed_by,
                    "reviewed_at": reviewed_at,
                },
            )
            if created:
                created_enrollment_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Created enrollment request id={request_id}; "
                        "requester=@{requester}; trip_id={trip_id}; status={status}"
                    ).format(
                        request_id=request_row.pk,
                        requester=seed.requester_username,
                        trip_id=seed.trip_id,
                        status=seed.status,
                    ),
                )
            else:
                updated_enrollment_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Updated enrollment request id={request_id}; "
                        "requester=@{requester}; trip_id={trip_id}; status={status}"
                    ).format(
                        request_id=request_row.pk,
                        requester=seed.requester_username,
                        trip_id=seed.trip_id,
                        status=seed.status,
                    ),
                )

        seeded_comment_rows: dict[str, Comment] = {}
        for seed in DEMO_COMMENT_SEEDS:
            member = get_member(seed.author_username)
            if member is None:
                skipped_comment_ops_count += 1
                continue

            target = resolve_comment_target(seed.target_type, seed.target_id)
            if target is None:
                skipped_comment_ops_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Skipping comment seed key={seed_key}; target not found "
                        "(type={target_type}, id={target_id})."
                    ).format(
                        seed_key=seed.key,
                        target_type=seed.target_type,
                        target_id=seed.target_id,
                    ),
                )
                continue

            comment_row = Comment.objects.filter(
                author=member,
                target_type=target.target_type,
                target_key=target.target_key,
                parent__isnull=True,
                text=seed.text,
            ).first()
            if comment_row is None:
                comment_row = Comment.objects.create(
                    author=member,
                    target_type=target.target_type,
                    target_key=target.target_key,
                    target_label=target.target_label,
                    target_url=target.target_url,
                    text=seed.text,
                    parent=None,
                )
                created_comment_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Created top-level comment key={seed_key}; id={comment_id}; "
                        "author=@{author}; target={target_type}:{target_key}"
                    ).format(
                        seed_key=seed.key,
                        comment_id=comment_row.pk,
                        author=seed.author_username,
                        target_type=target.target_type,
                        target_key=target.target_key,
                    ),
                )
            else:
                changed = False
                if comment_row.target_label != target.target_label:
                    comment_row.target_label = target.target_label
                    changed = True
                if comment_row.target_url != target.target_url:
                    comment_row.target_url = target.target_url
                    changed = True
                if changed:
                    comment_row.save(update_fields=["target_label", "target_url", "updated_at"])
                    updated_comment_count += 1
                    self._vprint(
                        verbose_enabled,
                        (
                            "Updated top-level comment key={seed_key}; id={comment_id}; "
                            "author=@{author}"
                        ).format(
                            seed_key=seed.key,
                            comment_id=comment_row.pk,
                            author=seed.author_username,
                        ),
                    )
                else:
                    self._vprint(
                        verbose_enabled,
                        (
                            "Top-level comment already up to date key={seed_key}; id={comment_id}"
                        ).format(
                            seed_key=seed.key,
                            comment_id=comment_row.pk,
                        ),
                    )

            seeded_comment_rows[seed.key] = comment_row

        for seed in DEMO_REPLY_SEEDS:
            member = get_member(seed.author_username)
            if member is None:
                skipped_comment_ops_count += 1
                continue

            parent_comment = seeded_comment_rows.get(seed.parent_key)
            if parent_comment is None:
                skipped_comment_ops_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Skipping reply seed author=@{author}; parent key '{parent_key}' "
                        "was not resolved."
                    ).format(
                        author=seed.author_username,
                        parent_key=seed.parent_key,
                    ),
                )
                continue

            reply_row = Comment.objects.filter(
                author=member,
                parent=parent_comment,
                text=seed.text,
            ).first()
            if reply_row is None:
                reply_row = Comment.objects.create(
                    author=member,
                    target_type=parent_comment.target_type,
                    target_key=parent_comment.target_key,
                    target_label=parent_comment.target_label,
                    target_url=parent_comment.target_url,
                    text=seed.text,
                    parent=parent_comment,
                )
                created_reply_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Created reply id={reply_id}; author=@{author}; parent_id={parent_id}"
                    ).format(
                        reply_id=reply_row.pk,
                        author=seed.author_username,
                        parent_id=parent_comment.pk,
                    ),
                )
            else:
                changed = False
                if reply_row.target_label != parent_comment.target_label:
                    reply_row.target_label = parent_comment.target_label
                    changed = True
                if reply_row.target_url != parent_comment.target_url:
                    reply_row.target_url = parent_comment.target_url
                    changed = True
                if changed:
                    reply_row.save(update_fields=["target_label", "target_url", "updated_at"])
                    updated_reply_count += 1
                    self._vprint(
                        verbose_enabled,
                        (
                            "Updated reply id={reply_id}; author=@{author}; parent_id={parent_id}"
                        ).format(
                            reply_id=reply_row.pk,
                            author=seed.author_username,
                            parent_id=parent_comment.pk,
                        ),
                    )
                else:
                    self._vprint(
                        verbose_enabled,
                        (
                            "Reply already up to date id={reply_id}; author=@{author}; parent_id={parent_id}"
                        ).format(
                            reply_id=reply_row.pk,
                            author=seed.author_username,
                            parent_id=parent_comment.pk,
                        ),
                    )

        for seed in DEMO_BOOKMARK_SEEDS:
            member = get_member(seed.member_username)
            if member is None:
                skipped_bookmark_count += 1
                continue

            target = resolve_bookmark_target(seed.target_type, seed.target_id)
            if target is None:
                skipped_bookmark_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Skipping bookmark seed member=@{member}; "
                        "target type={target_type}, id={target_id} not found."
                    ).format(
                        member=seed.member_username,
                        target_type=seed.target_type,
                        target_id=seed.target_id,
                    ),
                )
                continue

            bookmark_row, created = Bookmark.objects.get_or_create(
                member=member,
                target_type=target.target_type,
                target_key=target.target_key,
                defaults={
                    "target_label": target.target_label,
                    "target_url": target.target_url,
                },
            )
            if created:
                created_bookmark_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Created bookmark id={bookmark_id}; member=@{member}; "
                        "target={target_type}:{target_key}"
                    ).format(
                        bookmark_id=bookmark_row.pk,
                        member=seed.member_username,
                        target_type=target.target_type,
                        target_key=target.target_key,
                    ),
                )
            else:
                changed = False
                if bookmark_row.target_label != target.target_label:
                    bookmark_row.target_label = target.target_label
                    changed = True
                if bookmark_row.target_url != target.target_url:
                    bookmark_row.target_url = target.target_url
                    changed = True
                if changed:
                    bookmark_row.save(update_fields=["target_label", "target_url", "updated_at"])
                    updated_bookmark_count += 1
                    self._vprint(
                        verbose_enabled,
                        (
                            "Updated bookmark id={bookmark_id}; member=@{member}; "
                            "target={target_type}:{target_key}"
                        ).format(
                            bookmark_id=bookmark_row.pk,
                            member=seed.member_username,
                            target_type=target.target_type,
                            target_key=target.target_key,
                        ),
                    )
                else:
                    self._vprint(
                        verbose_enabled,
                        (
                            "Bookmark already up to date id={bookmark_id}; member=@{member}; "
                            "target={target_type}:{target_key}"
                        ).format(
                            bookmark_id=bookmark_row.pk,
                            member=seed.member_username,
                            target_type=target.target_type,
                            target_key=target.target_key,
                        ),
                    )

        for seed in DEMO_REVIEW_SEEDS:
            member = get_member(seed.member_username)
            if member is None:
                skipped_review_count += 1
                continue

            review_row, outcome, target = submit_review(
                member=member,
                target_type=seed.target_type,
                target_id=seed.target_id,
                rating=seed.rating,
                headline=seed.headline,
                body=seed.body,
            )
            if outcome == "created":
                created_review_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Created review id={review_id}; member=@{member}; "
                        "target={target}; rating={rating}"
                    ).format(
                        review_id=(review_row.pk if review_row is not None else "n/a"),
                        member=seed.member_username,
                        target=(
                            f"{target.target_type}:{target.target_key}" if target is not None else "n/a"
                        ),
                        rating=seed.rating,
                    ),
                )
            elif outcome == "updated":
                updated_review_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Updated review id={review_id}; member=@{member}; "
                        "target={target}; rating={rating}"
                    ).format(
                        review_id=(review_row.pk if review_row is not None else "n/a"),
                        member=seed.member_username,
                        target=(
                            f"{target.target_type}:{target.target_key}" if target is not None else "n/a"
                        ),
                        rating=seed.rating,
                    ),
                )
            else:
                skipped_review_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Skipped review member=@{member}; target_type={target_type}; "
                        "target_id={target_id}; outcome={outcome}"
                    ).format(
                        member=seed.member_username,
                        target_type=seed.target_type,
                        target_id=seed.target_id,
                        outcome=outcome,
                    ),
                )

        self.stdout.write(
            self.style.SUCCESS(
                "Activity bootstrap complete. "
                f"created_members={created_members_count}, "
                f"created_follows={created_follows_count}, "
                f"skipped_follows={skipped_follows_count}, "
                f"created_enrollment={created_enrollment_count}, "
                f"updated_enrollment={updated_enrollment_count}, "
                f"skipped_enrollment={skipped_enrollment_count}, "
                f"created_comments={created_comment_count}, "
                f"updated_comments={updated_comment_count}, "
                f"created_replies={created_reply_count}, "
                f"updated_replies={updated_reply_count}, "
                f"skipped_comment_ops={skipped_comment_ops_count}, "
                f"created_bookmarks={created_bookmark_count}, "
                f"updated_bookmarks={updated_bookmark_count}, "
                f"skipped_bookmarks={skipped_bookmark_count}, "
                f"created_reviews={created_review_count}, "
                f"updated_reviews={updated_review_count}, "
                f"skipped_reviews={skipped_review_count}"
            )
        )
