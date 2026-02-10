from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from io import BytesIO
from typing import Any, cast

from PIL import Image
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandParser
from django.utils import timezone

from media.models import submit_media_upload

UserModel = get_user_model()


def _build_sample_png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (1, 1), color=(32, 160, 141)).save(buffer, format="PNG")
    return buffer.getvalue()


SAMPLE_PNG_BYTES = _build_sample_png_bytes()
SAMPLE_MP4_BYTES = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42mp41"


@dataclass(frozen=True)
class MediaSeed:
    owner_username: str
    target_type: str
    target_id: str
    filename: str
    content_type: str
    caption: str
    payload_kind: str


BASE_MEDIA_SEEDS: tuple[MediaSeed, ...] = (
    MediaSeed(
        owner_username="mei",
        target_type="trip",
        target_id="101",
        filename="kyoto-cover.png",
        content_type="image/png",
        caption="Old market entrance before the first food stop.",
        payload_kind="image",
    ),
    MediaSeed(
        owner_username="arun",
        target_type="trip",
        target_id="102",
        filename="patagonia-brief.mp4",
        content_type="video/mp4",
        caption="Sunrise checkpoint briefing clip.",
        payload_kind="video",
    ),
    MediaSeed(
        owner_username="mei",
        target_type="blog",
        target_id="packing-for-swing-weather",
        filename="swing-weather-pack.png",
        content_type="image/png",
        caption="Layering map used in this post.",
        payload_kind="image",
    ),
)


class Command(BaseCommand):
    help = "Create or refresh demo media uploads for trip/blog/review attachment flows."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--create-missing-members",
            action="store_true",
            help="Create missing demo members before media seeding.",
        )
        parser.add_argument(
            "--create-missing-targets",
            action="store_true",
            help="Create missing trip/blog/review targets before media seeding.",
        )
        parser.add_argument(
            "--demo-password",
            default="TapneDemoPass!123",
            help="Password used when missing members are created.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print detailed progress for each media seed row.",
        )

    def _vprint(self, verbose_enabled: bool, message: str) -> None:
        if verbose_enabled:
            self.stdout.write(f"[media][verbose] {message}")

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
                    f"Skipping @{username}; member does not exist and "
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

    def _ensure_trip_target(
        self,
        *,
        trip_id: int,
        host: Any,
        create_missing_targets: bool,
        verbose_enabled: bool,
    ) -> tuple[bool, bool]:
        try:
            trip_model = apps.get_model("trips", "Trip")
        except LookupError:
            self._vprint(verbose_enabled, "Trip model unavailable; skipping trip target ensure.")
            return False, False

        trip = trip_model.objects.filter(pk=trip_id).first()
        if trip is not None:
            trip_host_id = int(getattr(trip, "host_id", 0) or 0)
            if trip_host_id == int(getattr(host, "pk", 0) or 0):
                return True, False

            if not create_missing_targets:
                self._vprint(
                    verbose_enabled,
                    (
                        f"Trip #{trip_id} exists but is not owned by @{host.username}; "
                        "--create-missing-targets is disabled."
                    ),
                )
                return False, False

            trip_update_fields: dict[str, object] = {"host": host}
            if hasattr(trip, "updated_at"):
                trip_update_fields["updated_at"] = timezone.now()
            trip_model.objects.filter(pk=trip_id).update(**trip_update_fields)
            self._vprint(verbose_enabled, f"Reassigned trip #{trip_id} to @{host.username}")
            return True, True

        if not create_missing_targets:
            self._vprint(verbose_enabled, f"Trip #{trip_id} missing and --create-missing-targets is disabled.")
            return False, False

        starts_at = timezone.now() + timedelta(days=14)
        trip_model.objects.create(
            pk=trip_id,
            host=host,
            title=f"Seed trip #{trip_id}",
            summary="Seeded trip row for media attachment bootstrap.",
            description="Generated by bootstrap_media to ensure media upload wiring has a live trip target.",
            destination="Seed destination",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(days=2),
            traffic_score=10,
            is_published=True,
        )
        self._vprint(verbose_enabled, f"Created missing trip target #{trip_id} for @{host.username}")
        return True, True

    def _ensure_blog_target(
        self,
        *,
        slug: str,
        author: Any,
        create_missing_targets: bool,
        verbose_enabled: bool,
    ) -> tuple[bool, bool]:
        try:
            blog_model = apps.get_model("blogs", "Blog")
        except LookupError:
            self._vprint(verbose_enabled, "Blog model unavailable; skipping blog target ensure.")
            return False, False

        blog = blog_model.objects.filter(slug__iexact=slug).first()
        if blog is not None:
            blog_author_id = int(getattr(blog, "author_id", 0) or 0)
            if blog_author_id == int(getattr(author, "pk", 0) or 0):
                return True, False

            if not create_missing_targets:
                self._vprint(
                    verbose_enabled,
                    (
                        f"Blog '{slug}' exists but is not owned by @{author.username}; "
                        "--create-missing-targets is disabled."
                    ),
                )
                return False, False

            blog_update_fields: dict[str, object] = {"author": author}
            if hasattr(blog, "updated_at"):
                blog_update_fields["updated_at"] = timezone.now()
            blog_model.objects.filter(pk=blog.pk).update(**blog_update_fields)
            self._vprint(verbose_enabled, f"Reassigned blog '{slug}' to @{author.username}")
            return True, True

        if not create_missing_targets:
            self._vprint(verbose_enabled, f"Blog '{slug}' missing and --create-missing-targets is disabled.")
            return False, False

        blog_model.objects.create(
            author=author,
            slug=slug,
            title=f"Seed blog {slug.replace('-', ' ').title()}",
            excerpt="Seeded blog row for media attachment bootstrap.",
            body="Generated by bootstrap_media to ensure media upload wiring has a live blog target.",
            reads=10,
            reviews_count=0,
            is_published=True,
        )
        self._vprint(verbose_enabled, f"Created missing blog target '{slug}' for @{author.username}")
        return True, True

    def _resolve_or_create_review_target(
        self,
        *,
        owner: Any,
        create_missing_targets: bool,
        verbose_enabled: bool,
    ) -> tuple[str | None, bool]:
        try:
            review_model = apps.get_model("reviews", "Review")
        except LookupError:
            self._vprint(verbose_enabled, "Review model unavailable; skipping review media seed.")
            return None, False

        existing_review = review_model.objects.filter(author=owner).order_by("-created_at", "-pk").first()
        if existing_review is not None:
            return str(int(existing_review.pk)), False

        if not create_missing_targets:
            self._vprint(
                verbose_enabled,
                (
                    f"No review found for @{owner.username}; "
                    "--create-missing-targets is disabled so review seed will be skipped."
                ),
            )
            return None, False

        # Try to create a minimal review targeting trip #101.
        trip_ready, _trip_changed = self._ensure_trip_target(
            trip_id=101,
            host=owner,
            create_missing_targets=True,
            verbose_enabled=verbose_enabled,
        )
        if not trip_ready:
            self._vprint(verbose_enabled, f"Could not ensure trip target for @{owner.username}; review seed skipped.")
            return None, False

        from reviews.models import submit_review as submit_review_row

        review_row, outcome, _resolved_target = submit_review_row(
            member=owner,
            target_type="trip",
            target_id="101",
            rating=5,
            headline="Seed review for media",
            body="Generated so media attachments can be wired to review rows.",
        )
        if review_row is None or outcome not in {"created", "updated"}:
            self._vprint(verbose_enabled, f"Could not create review seed for @{owner.username}; outcome={outcome}")
            return None, False

        self._vprint(verbose_enabled, f"Created review target #{review_row.pk} for @{owner.username}")
        return str(int(review_row.pk)), True

    def _make_uploaded_file(self, *, seed: MediaSeed) -> SimpleUploadedFile:
        content = SAMPLE_PNG_BYTES if seed.payload_kind == "image" else SAMPLE_MP4_BYTES
        return SimpleUploadedFile(
            name=seed.filename,
            content=content,
            content_type=seed.content_type,
        )

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        verbose_enabled = bool(options.get("verbose"))
        create_missing_members = bool(options.get("create_missing_members"))
        create_missing_targets = bool(options.get("create_missing_targets"))
        demo_password = str(options.get("demo_password") or "TapneDemoPass!123")

        self.stdout.write("Bootstrapping media uploads for trip/blog/review targets...")
        self._vprint(
            verbose_enabled,
            (
                "create_missing_members={members}; create_missing_targets={targets}"
                .format(
                    members=create_missing_members,
                    targets=create_missing_targets,
                )
            ),
        )

        created_members_count = 0
        created_targets_count = 0
        created_uploads_count = 0
        attached_existing_count = 0
        already_attached_count = 0
        skipped_count = 0

        member_cache: dict[str, Any | None] = {}

        def resolve_member(username: str) -> Any | None:
            nonlocal created_members_count

            cache_key = username.lower()
            if cache_key in member_cache:
                return member_cache[cache_key]

            member, member_created = self._resolve_member(
                username=username,
                create_missing_members=create_missing_members,
                demo_password=demo_password,
                verbose_enabled=verbose_enabled,
            )
            if member_created:
                created_members_count += 1
            member_cache[cache_key] = member
            return member

        # Base trip/blog seeds.
        for seed in BASE_MEDIA_SEEDS:
            member = resolve_member(seed.owner_username)
            if member is None:
                skipped_count += 1
                continue

            target_ready = False
            target_changed = False
            if seed.target_type == "trip":
                target_ready, target_changed = self._ensure_trip_target(
                    trip_id=int(seed.target_id),
                    host=member,
                    create_missing_targets=create_missing_targets,
                    verbose_enabled=verbose_enabled,
                )
            elif seed.target_type == "blog":
                target_ready, target_changed = self._ensure_blog_target(
                    slug=seed.target_id,
                    author=member,
                    create_missing_targets=create_missing_targets,
                    verbose_enabled=verbose_enabled,
                )

            if not target_ready:
                skipped_count += 1
                continue

            if target_changed:
                created_targets_count += 1

            uploaded_file = self._make_uploaded_file(seed=seed)
            asset, attachment, outcome, _target = submit_media_upload(
                member=member,
                target_type=seed.target_type,
                target_id=seed.target_id,
                uploaded_file=uploaded_file,
                caption=seed.caption,
            )

            if outcome == "created":
                created_uploads_count += 1
            elif outcome == "attached-existing":
                attached_existing_count += 1
            elif outcome == "already-attached":
                already_attached_count += 1
            else:
                skipped_count += 1

            self._vprint(
                verbose_enabled,
                (
                    "Seed outcome={outcome}; owner=@{owner}; target={target_type}:{target_id}; "
                    "attachment_id={attachment_id}; asset_id={asset_id}"
                ).format(
                    outcome=outcome,
                    owner=seed.owner_username,
                    target_type=seed.target_type,
                    target_id=seed.target_id,
                    attachment_id=(attachment.pk if attachment is not None else "n/a"),
                    asset_id=(asset.pk if asset is not None else "n/a"),
                ),
            )

        # Optional review seed uses one review row owned by mei.
        review_owner = resolve_member("mei")
        if review_owner is not None:
            review_target_id, review_target_created = self._resolve_or_create_review_target(
                owner=review_owner,
                create_missing_targets=create_missing_targets,
                verbose_enabled=verbose_enabled,
            )
            if review_target_id is None:
                skipped_count += 1
            else:
                if review_target_created:
                    created_targets_count += 1
                review_seed = MediaSeed(
                    owner_username="mei",
                    target_type="review",
                    target_id=review_target_id,
                    filename="review-proof.png",
                    content_type="image/png",
                    caption="Attachment linked directly to a review row.",
                    payload_kind="image",
                )
                uploaded_file = self._make_uploaded_file(seed=review_seed)
                asset, attachment, outcome, _target = submit_media_upload(
                    member=review_owner,
                    target_type=review_seed.target_type,
                    target_id=review_seed.target_id,
                    uploaded_file=uploaded_file,
                    caption=review_seed.caption,
                )

                if outcome == "created":
                    created_uploads_count += 1
                elif outcome == "attached-existing":
                    attached_existing_count += 1
                elif outcome == "already-attached":
                    already_attached_count += 1
                else:
                    skipped_count += 1

                self._vprint(
                    verbose_enabled,
                    (
                        "Review seed outcome={outcome}; owner=@{owner}; review_id={review_id}; "
                        "attachment_id={attachment_id}; asset_id={asset_id}"
                    ).format(
                        outcome=outcome,
                        owner=review_seed.owner_username,
                        review_id=review_seed.target_id,
                        attachment_id=(attachment.pk if attachment is not None else "n/a"),
                        asset_id=(asset.pk if asset is not None else "n/a"),
                    ),
                )

        self.stdout.write(
            self.style.SUCCESS(
                "Media bootstrap complete. "
                f"created_members={created_members_count}, "
                f"created_targets={created_targets_count}, "
                f"created_uploads={created_uploads_count}, "
                f"attached_existing={attached_existing_count}, "
                f"already_attached={already_attached_count}, "
                f"skipped={skipped_count}"
            )
        )
