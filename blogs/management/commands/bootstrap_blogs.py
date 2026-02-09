from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandParser

from blogs.models import Blog

UserModel = get_user_model()


@dataclass(frozen=True)
class BlogSeed:
    blog_id: int
    author_username: str
    slug: str
    title: str
    excerpt: str
    body: str
    reads: int
    reviews_count: int


DEMO_BLOG_SEEDS: tuple[BlogSeed, ...] = (
    BlogSeed(
        blog_id=301,
        author_username="mei",
        slug="packing-for-swing-weather",
        title="Packing for swing-weather trips without overloading",
        excerpt="A practical split-list approach for weather shifts when you only want one carry-on setup.",
        body="Use a modular layer stack, then reserve one slot for location-specific gear.",
        reads=9500,
        reviews_count=142,
    ),
    BlogSeed(
        blog_id=302,
        author_username="arun",
        slug="first-group-trip-ops-checklist",
        title="First group-trip operations checklist",
        excerpt="Pre-trip ops that prevent most host-side issues: permissions, comms windows, and pacing handoffs.",
        body="Map operational failure points first, then assign one fallback per checkpoint.",
        reads=7200,
        reviews_count=98,
    ),
    BlogSeed(
        blog_id=303,
        author_username="sahar",
        slug="how-to-run-a-desert-route",
        title="How to run a desert route without chaos",
        excerpt="A logistics-first system for market pickups, long transfers, and camp sequencing.",
        body="Fix transport and hydration constraints early, then fit storytelling around reliable checkpoints.",
        reads=6100,
        reviews_count=76,
    ),
)


class Command(BaseCommand):
    help = "Create or refresh demo blog rows used by list/detail/search flows."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--create-missing-authors",
            action="store_true",
            help="Create missing blog authors before seeding blog rows.",
        )
        parser.add_argument(
            "--demo-password",
            default="TapneDemoPass!123",
            help="Password used when --create-missing-authors creates user rows.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print detailed progress lines for each seeded blog.",
        )

    def _vprint(self, verbose_enabled: bool, message: str) -> None:
        if verbose_enabled:
            self.stdout.write(f"[blogs][verbose] {message}")

    def _resolve_author(
        self,
        *,
        username: str,
        create_missing_authors: bool,
        demo_password: str,
        verbose_enabled: bool,
    ) -> tuple[Any | None, bool]:
        author = cast(Any | None, UserModel.objects.filter(username__iexact=username).first())
        if author:
            if author.username != username:
                author.username = username
                author.save(update_fields=["username"])
                self._vprint(verbose_enabled, f"Normalized author username casing to @{username}")
            return author, False

        if not create_missing_authors:
            self._vprint(
                verbose_enabled,
                (
                    f"Skipping author @{username}; user does not exist and "
                    "--create-missing-authors is disabled."
                ),
            )
            return None, False

        author = UserModel.objects.create_user(
            username=username,
            email=f"{username}@tapne.local",
            password=demo_password,
        )
        self._vprint(verbose_enabled, f"Created missing author @{username}")
        return author, True

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        verbose_enabled = bool(options.get("verbose"))
        create_missing_authors = bool(options.get("create_missing_authors"))
        demo_password = str(options.get("demo_password") or "TapneDemoPass!123")

        self.stdout.write("Bootstrapping blog catalog records...")
        self._vprint(verbose_enabled, f"create_missing_authors={create_missing_authors}")

        created_authors_count = 0
        created_blogs_count = 0
        updated_blogs_count = 0
        skipped_blogs_count = 0

        for seed in DEMO_BLOG_SEEDS:
            author, author_created = self._resolve_author(
                username=seed.author_username,
                create_missing_authors=create_missing_authors,
                demo_password=demo_password,
                verbose_enabled=verbose_enabled,
            )
            if author_created:
                created_authors_count += 1

            if author is None:
                skipped_blogs_count += 1
                continue

            blog, created = Blog.objects.update_or_create(
                pk=seed.blog_id,
                defaults={
                    "author": author,
                    "slug": seed.slug,
                    "title": seed.title,
                    "excerpt": seed.excerpt,
                    "body": seed.body,
                    "reads": seed.reads,
                    "reviews_count": seed.reviews_count,
                    "is_published": True,
                },
            )

            if created:
                created_blogs_count += 1
                self._vprint(verbose_enabled, f"Created blog slug={blog.slug} for @{seed.author_username}")
            else:
                updated_blogs_count += 1
                self._vprint(verbose_enabled, f"Updated blog slug={blog.slug} for @{seed.author_username}")

        self.stdout.write(
            self.style.SUCCESS(
                "Blogs bootstrap complete. "
                f"created_authors={created_authors_count}, "
                f"created_blogs={created_blogs_count}, "
                f"updated_blogs={updated_blogs_count}, "
                f"skipped={skipped_blogs_count}"
            )
        )
