from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandParser

from interactions.models import (
    Comment,
    DirectMessage,
    get_or_create_dm_thread_for_members,
    resolve_comment_target,
)

UserModel = get_user_model()


@dataclass(frozen=True)
class CommentSeed:
    key: str
    member_username: str
    target_type: str
    target_id: str
    text: str


@dataclass(frozen=True)
class ReplySeed:
    member_username: str
    parent_key: str
    text: str


@dataclass(frozen=True)
class DMMessageSeed:
    sender_username: str
    text: str


@dataclass(frozen=True)
class DMThreadSeed:
    member_one_username: str
    member_two_username: str
    messages: tuple[DMMessageSeed, ...]


COMMENT_SEEDS: tuple[CommentSeed, ...] = (
    CommentSeed(
        key="c1",
        member_username="mei",
        target_type="trip",
        target_id="101",
        text="Would love to join this route. The food sequencing looks practical.",
    ),
    CommentSeed(
        key="c2",
        member_username="arun",
        target_type="trip",
        target_id="101",
        text="How strict is the morning start window on day two?",
    ),
    CommentSeed(
        key="c3",
        member_username="sahar",
        target_type="blog",
        target_id="packing-for-swing-weather",
        text="Great layering checklist. I use a very similar carry-on split.",
    ),
    CommentSeed(
        key="c4",
        member_username="mei",
        target_type="blog",
        target_id="how-to-run-a-desert-route",
        text="The hydration checkpoint callout is especially useful.",
    ),
)

REPLY_SEEDS: tuple[ReplySeed, ...] = (
    ReplySeed(
        member_username="arun",
        parent_key="c1",
        text="Same here. I can help with early logistics if needed.",
    ),
    ReplySeed(
        member_username="sahar",
        parent_key="c1",
        text="I like how the route keeps walking blocks compact.",
    ),
    ReplySeed(
        member_username="mei",
        parent_key="c3",
        text="Thanks. The goal was to keep it realistic for one-bag travel.",
    ),
)

DM_THREAD_SEEDS: tuple[DMThreadSeed, ...] = (
    DMThreadSeed(
        member_one_username="mei",
        member_two_username="arun",
        messages=(
            DMMessageSeed(
                sender_username="mei",
                text="Want to co-host the opening segment next month?",
            ),
            DMMessageSeed(
                sender_username="arun",
                text="Yes, I can lock an ops checklist tonight.",
            ),
        ),
    ),
    DMThreadSeed(
        member_one_username="arun",
        member_two_username="sahar",
        messages=(
            DMMessageSeed(
                sender_username="arun",
                text="Can you share your transfer timing template?",
            ),
            DMMessageSeed(
                sender_username="sahar",
                text="Sending it now. It includes fallback timing buffers.",
            ),
        ),
    ),
)


class Command(BaseCommand):
    help = "Create or refresh demo comments/replies and DM rows for the interactions app."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--create-missing-members",
            action="store_true",
            help="Create missing demo members before applying interactions seeds.",
        )
        parser.add_argument(
            "--demo-password",
            default="TapneDemoPass!123",
            help="Password used when --create-missing-members creates users.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print detailed progress for comment/reply/DM seed operations.",
        )

    def _vprint(self, verbose_enabled: bool, message: str) -> None:
        if verbose_enabled:
            self.stdout.write(f"[interactions][verbose] {message}")

    def _clean_text(self, value: object) -> str:
        return " ".join(str(value or "").strip().split())

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

        self.stdout.write("Bootstrapping interactions comments, replies, and direct messages...")
        self._vprint(verbose_enabled, f"create_missing_members={create_missing_members}")

        created_members_count = 0
        created_comments_count = 0
        existing_comments_count = 0
        created_replies_count = 0
        existing_replies_count = 0
        skipped_comment_rows = 0
        created_threads_count = 0
        existing_threads_count = 0
        created_messages_count = 0
        existing_messages_count = 0
        skipped_messages_count = 0

        top_level_comments_by_key: dict[str, Comment] = {}
        member_cache: dict[str, Any] = {}

        def get_member(username: str) -> Any | None:
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

        for seed in COMMENT_SEEDS:
            member = get_member(seed.member_username)
            if member is None:
                skipped_comment_rows += 1
                continue

            target = resolve_comment_target(seed.target_type, seed.target_id)
            if target is None:
                skipped_comment_rows += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Skipping comment seed key={key}; type={target_type}; target_id={target_id}; target missing"
                        .format(
                            key=seed.key,
                            target_type=seed.target_type,
                            target_id=seed.target_id,
                        )
                    ),
                )
                continue

            cleaned_text = self._clean_text(seed.text)
            if not cleaned_text:
                skipped_comment_rows += 1
                self._vprint(verbose_enabled, f"Skipping comment seed key={seed.key}; text was empty after clean.")
                continue

            existing_comment = (
                Comment.objects.filter(
                    author=member,
                    target_type=target.target_type,
                    target_key=target.target_key,
                    parent__isnull=True,
                    text=cleaned_text,
                )
                .order_by("-pk")
                .first()
            )

            if existing_comment is not None:
                changed = False
                if existing_comment.target_label != target.target_label:
                    existing_comment.target_label = target.target_label
                    changed = True
                if existing_comment.target_url != target.target_url:
                    existing_comment.target_url = target.target_url
                    changed = True
                if changed:
                    existing_comment.save(update_fields=["target_label", "target_url", "updated_at"])

                top_level_comments_by_key[seed.key] = existing_comment
                existing_comments_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Top-level comment already present key={key}; comment_id={comment_id}".format(
                            key=seed.key,
                            comment_id=existing_comment.pk,
                        )
                    ),
                )
                continue

            created_comment = Comment.objects.create(
                author=member,
                target_type=target.target_type,
                target_key=target.target_key,
                target_label=target.target_label,
                target_url=target.target_url,
                text=cleaned_text,
                parent=None,
            )
            top_level_comments_by_key[seed.key] = created_comment
            created_comments_count += 1
            self._vprint(
                verbose_enabled,
                (
                    "Created top-level comment key={key}; comment_id={comment_id}; target={target_type}:{target_key}"
                    .format(
                        key=seed.key,
                        comment_id=created_comment.pk,
                        target_type=target.target_type,
                        target_key=target.target_key,
                    )
                ),
            )

        for seed in REPLY_SEEDS:
            member = get_member(seed.member_username)
            if member is None:
                skipped_comment_rows += 1
                continue

            parent_comment = top_level_comments_by_key.get(seed.parent_key)
            if parent_comment is None:
                skipped_comment_rows += 1
                self._vprint(
                    verbose_enabled,
                    f"Skipping reply seed parent_key={seed.parent_key}; parent comment not available.",
                )
                continue

            cleaned_text = self._clean_text(seed.text)
            if not cleaned_text:
                skipped_comment_rows += 1
                self._vprint(
                    verbose_enabled,
                    f"Skipping reply seed parent_key={seed.parent_key}; text was empty after clean.",
                )
                continue

            existing_reply = (
                Comment.objects.filter(
                    author=member,
                    parent=parent_comment,
                    text=cleaned_text,
                )
                .order_by("-pk")
                .first()
            )
            if existing_reply is not None:
                existing_replies_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Reply already present parent_key={parent_key}; reply_id={reply_id}".format(
                            parent_key=seed.parent_key,
                            reply_id=existing_reply.pk,
                        )
                    ),
                )
                continue

            created_reply = Comment.objects.create(
                author=member,
                target_type=parent_comment.target_type,
                target_key=parent_comment.target_key,
                target_label=parent_comment.target_label,
                target_url=parent_comment.target_url,
                text=cleaned_text,
                parent=parent_comment,
            )
            created_replies_count += 1
            self._vprint(
                verbose_enabled,
                (
                    "Created reply parent_key={parent_key}; reply_id={reply_id}".format(
                        parent_key=seed.parent_key,
                        reply_id=created_reply.pk,
                    )
                ),
            )

        for seed in DM_THREAD_SEEDS:
            member_one = get_member(seed.member_one_username)
            member_two = get_member(seed.member_two_username)
            if member_one is None or member_two is None:
                skipped_messages_count += len(seed.messages)
                continue

            thread, created_thread, outcome = get_or_create_dm_thread_for_members(
                member=member_one,
                other_member=member_two,
            )
            if thread is None:
                skipped_messages_count += len(seed.messages)
                self._vprint(
                    verbose_enabled,
                    (
                        "Skipping DM thread seed @{member_one} <-> @{member_two}; outcome={outcome}".format(
                            member_one=seed.member_one_username,
                            member_two=seed.member_two_username,
                            outcome=outcome,
                        )
                    ),
                )
                continue

            if created_thread:
                created_threads_count += 1
            else:
                existing_threads_count += 1

            participant_map = {
                str(getattr(thread.member_one, "username", "") or "").strip().lower(): thread.member_one,
                str(getattr(thread.member_two, "username", "") or "").strip().lower(): thread.member_two,
            }

            for message_seed in seed.messages:
                sender = participant_map.get(message_seed.sender_username.lower())
                if sender is None:
                    skipped_messages_count += 1
                    self._vprint(
                        verbose_enabled,
                        (
                            "Skipping DM message; sender @{sender} is not a participant in thread id={thread_id}"
                            .format(
                                sender=message_seed.sender_username,
                                thread_id=thread.pk,
                            )
                        ),
                    )
                    continue

                cleaned_text = self._clean_text(message_seed.text)
                if not cleaned_text:
                    skipped_messages_count += 1
                    self._vprint(
                        verbose_enabled,
                        f"Skipping DM message in thread id={thread.pk}; text was empty after clean.",
                    )
                    continue

                existing_message = (
                    DirectMessage.objects.filter(
                        thread=thread,
                        sender=sender,
                        body=cleaned_text,
                    )
                    .order_by("-pk")
                    .first()
                )
                if existing_message is not None:
                    existing_messages_count += 1
                    self._vprint(
                        verbose_enabled,
                        (
                            "DM message already present thread_id={thread_id}; message_id={message_id}".format(
                                thread_id=thread.pk,
                                message_id=existing_message.pk,
                            )
                        ),
                    )
                    continue

                created_message = DirectMessage.objects.create(
                    thread=thread,
                    sender=sender,
                    body=cleaned_text,
                )
                thread.touch()
                created_messages_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Created DM message thread_id={thread_id}; message_id={message_id}; sender=@{sender}".format(
                            thread_id=thread.pk,
                            message_id=created_message.pk,
                            sender=message_seed.sender_username,
                        )
                    ),
                )

        self.stdout.write(
            self.style.SUCCESS(
                "Interactions bootstrap complete. "
                f"created_members={created_members_count}, "
                f"created_comments={created_comments_count}, "
                f"existing_comments={existing_comments_count}, "
                f"created_replies={created_replies_count}, "
                f"existing_replies={existing_replies_count}, "
                f"skipped_comment_rows={skipped_comment_rows}, "
                f"created_threads={created_threads_count}, "
                f"existing_threads={existing_threads_count}, "
                f"created_messages={created_messages_count}, "
                f"existing_messages={existing_messages_count}, "
                f"skipped_messages={skipped_messages_count}"
            )
        )
