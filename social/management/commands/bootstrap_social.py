from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandParser

from social.models import (
    Bookmark,
    FollowRelation,
    resolve_bookmark_target,
    sync_member_follow_usernames,
)

UserModel = get_user_model()


@dataclass(frozen=True)
class FollowSeed:
    follower_username: str
    following_username: str


@dataclass(frozen=True)
class BookmarkSeed:
    member_username: str
    target_type: str
    target_id: str


DEMO_FOLLOW_SEEDS: tuple[FollowSeed, ...] = (
    FollowSeed(follower_username="mei", following_username="arun"),
    FollowSeed(follower_username="arun", following_username="sahar"),
    FollowSeed(follower_username="sahar", following_username="mei"),
)

DEMO_BOOKMARK_SEEDS: tuple[BookmarkSeed, ...] = (
    BookmarkSeed(member_username="mei", target_type="trip", target_id="101"),
    BookmarkSeed(
        member_username="mei",
        target_type="blog",
        target_id="packing-for-swing-weather",
    ),
    BookmarkSeed(member_username="mei", target_type="user", target_id="sahar"),
    BookmarkSeed(member_username="arun", target_type="trip", target_id="102"),
    BookmarkSeed(
        member_username="arun",
        target_type="blog",
        target_id="first-group-trip-ops-checklist",
    ),
    BookmarkSeed(member_username="arun", target_type="user", target_id="mei"),
    BookmarkSeed(member_username="sahar", target_type="trip", target_id="103"),
    BookmarkSeed(
        member_username="sahar",
        target_type="blog",
        target_id="how-to-run-a-desert-route",
    ),
    BookmarkSeed(member_username="sahar", target_type="user", target_id="arun"),
)


class Command(BaseCommand):
    help = "Create or refresh demo follow and bookmark rows for the social app."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--create-missing-members",
            action="store_true",
            help="Create missing demo members before applying social seeds.",
        )
        parser.add_argument(
            "--demo-password",
            default="TapneDemoPass!123",
            help="Password used when --create-missing-members creates new users.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print detailed progress for follow/bookmark seed operations.",
        )

    def _vprint(self, verbose_enabled: bool, message: str) -> None:
        if verbose_enabled:
            self.stdout.write(f"[social][verbose] {message}")

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

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        verbose_enabled = bool(options.get("verbose"))
        create_missing_members = bool(options.get("create_missing_members"))
        demo_password = str(options.get("demo_password") or "TapneDemoPass!123")

        self.stdout.write("Bootstrapping social follow and bookmark records...")
        self._vprint(verbose_enabled, f"create_missing_members={create_missing_members}")

        created_members_count = 0
        created_follows_count = 0
        skipped_follows_count = 0
        created_bookmarks_count = 0
        updated_bookmarks_count = 0
        skipped_bookmarks_count = 0
        touched_member_ids: set[int] = set()

        for seed in DEMO_FOLLOW_SEEDS:
            follower, follower_created = self._resolve_member(
                username=seed.follower_username,
                create_missing_members=create_missing_members,
                demo_password=demo_password,
                verbose_enabled=verbose_enabled,
            )
            if follower_created:
                created_members_count += 1

            following, following_created = self._resolve_member(
                username=seed.following_username,
                create_missing_members=create_missing_members,
                demo_password=demo_password,
                verbose_enabled=verbose_enabled,
            )
            if following_created:
                created_members_count += 1

            if follower is None or following is None:
                skipped_follows_count += 1
                continue

            if int(follower.pk) == int(following.pk):
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
            touched_member_ids.add(int(follower.pk))

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

        for seed in DEMO_BOOKMARK_SEEDS:
            member, member_created = self._resolve_member(
                username=seed.member_username,
                create_missing_members=create_missing_members,
                demo_password=demo_password,
                verbose_enabled=verbose_enabled,
            )
            if member_created:
                created_members_count += 1

            if member is None:
                skipped_bookmarks_count += 1
                continue

            target = resolve_bookmark_target(seed.target_type, seed.target_id)
            if target is None:
                skipped_bookmarks_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Skipping bookmark seed member=@{member}; type={target_type}; id={target_id}; target missing"
                        .format(
                            member=seed.member_username,
                            target_type=seed.target_type,
                            target_id=seed.target_id,
                        )
                    ),
                )
                continue

            bookmark, created = Bookmark.objects.get_or_create(
                member=member,
                target_type=target.target_type,
                target_key=target.target_key,
                defaults={
                    "target_label": target.target_label,
                    "target_url": target.target_url,
                },
            )
            touched_member_ids.add(int(member.pk))

            if created:
                created_bookmarks_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Created bookmark member=@{member}; type={target_type}; key={target_key}".format(
                            member=seed.member_username,
                            target_type=target.target_type,
                            target_key=target.target_key,
                        )
                    ),
                )
            else:
                changed = False
                if bookmark.target_label != target.target_label:
                    bookmark.target_label = target.target_label
                    changed = True
                if bookmark.target_url != target.target_url:
                    bookmark.target_url = target.target_url
                    changed = True

                if changed:
                    bookmark.save(update_fields=["target_label", "target_url", "updated_at"])
                    updated_bookmarks_count += 1
                    self._vprint(
                        verbose_enabled,
                        (
                            "Updated bookmark member=@{member}; type={target_type}; key={target_key}"
                            .format(
                                member=seed.member_username,
                                target_type=target.target_type,
                                target_key=target.target_key,
                            )
                        ),
                    )
                else:
                    self._vprint(
                        verbose_enabled,
                        (
                            "Bookmark already up to date member=@{member}; type={target_type}; key={target_key}"
                            .format(
                                member=seed.member_username,
                                target_type=target.target_type,
                                target_key=target.target_key,
                            )
                        ),
                    )

        for member_id in sorted(touched_member_ids):
            member = UserModel.objects.filter(pk=member_id).first()
            if member is None:
                continue
            synced_usernames = sync_member_follow_usernames(member)
            self._vprint(
                verbose_enabled,
                f"Synced feed follow preferences for @{member.username}: {synced_usernames}",
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Social bootstrap complete. "
                f"created_members={created_members_count}, "
                f"created_follows={created_follows_count}, "
                f"skipped_follows={skipped_follows_count}, "
                f"created_bookmarks={created_bookmarks_count}, "
                f"updated_bookmarks={updated_bookmarks_count}, "
                f"skipped_bookmarks={skipped_bookmarks_count}"
            )
        )
