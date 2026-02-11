from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandParser

from runtime.models import (
    finalize_idempotency_key,
    increment_runtime_counter,
    queue_runtime_task,
    reserve_idempotency_key,
    snapshot_runtime_counter,
    warm_feed_cache_for_user,
    warm_search_cache_for_user,
)

UserModel = get_user_model()


@dataclass(frozen=True)
class RuntimeSeed:
    username: str
    query: str
    result_type: str


RUNTIME_SEEDS: tuple[RuntimeSeed, ...] = (
    RuntimeSeed(username="mei", query="food itinerary", result_type="all"),
    RuntimeSeed(username="arun", query="mountain camp", result_type="trips"),
    RuntimeSeed(username="sahar", query="desert route", result_type="blogs"),
    RuntimeSeed(username="nora", query="host profile", result_type="users"),
)


class Command(BaseCommand):
    help = "Warm runtime cache shelves, idempotency guards, counters, and task queue envelopes."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--create-missing-members",
            action="store_true",
            help="Create missing seeded members before warming runtime shelves.",
        )
        parser.add_argument(
            "--demo-password",
            default="TapneDemoPass!123",
            help="Password used when --create-missing-members creates users.",
        )
        parser.add_argument(
            "--search-query",
            default="tapne",
            help="Override the query used for seeded search cache payloads.",
        )
        parser.add_argument(
            "--search-type",
            default="all",
            help="Override the result type used for seeded search cache payloads.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print detailed progress lines for runtime bootstrap operations.",
        )

    def _vprint(self, verbose_enabled: bool, message: str) -> None:
        if verbose_enabled:
            self.stdout.write(f"[runtime][verbose] {message}")

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
        search_query_override = str(options.get("search_query") or "tapne").strip()
        search_type_override = str(options.get("search_type") or "all").strip().lower() or "all"

        self.stdout.write("Bootstrapping runtime shelves, guards, counters, and queue envelopes...")
        self._vprint(verbose_enabled, f"create_missing_members={create_missing_members}")

        created_members_count = 0
        warmed_feed_cache_count = 0
        warmed_search_cache_count = 0
        reserved_idempotency_count = 0
        duplicate_idempotency_count = 0
        queued_task_count = 0
        counter_snapshots_count = 0
        skipped_count = 0

        guest_feed_key = warm_feed_cache_for_user(
            None,
            payload={
                "mode": "guest-runtime-cache",
                "reason": "Guest runtime feed shelf warmed by bootstrap_runtime.",
            },
        )
        warmed_feed_cache_count += 1
        self._vprint(verbose_enabled, f"Warmed guest feed cache key={guest_feed_key}")

        guest_search_key = warm_search_cache_for_user(
            None,
            query=search_query_override,
            result_type=search_type_override,
            payload={
                "mode": "guest-runtime-cache",
                "query": search_query_override,
                "result_type": search_type_override,
            },
        )
        warmed_search_cache_count += 1
        self._vprint(verbose_enabled, f"Warmed guest search cache key={guest_search_key}")

        for seed in RUNTIME_SEEDS:
            member, member_created = self._resolve_member(
                username=seed.username,
                create_missing_members=create_missing_members,
                demo_password=demo_password,
                verbose_enabled=verbose_enabled,
            )
            if member_created:
                created_members_count += 1
            if member is None:
                skipped_count += 1
                continue

            effective_query = search_query_override or seed.query
            effective_type = search_type_override or seed.result_type

            feed_cache_key = warm_feed_cache_for_user(
                member,
                payload={
                    "mode": "member-runtime-cache",
                    "member_username": seed.username,
                    "reason": "Seeded by bootstrap_runtime for feed shelf warmup.",
                },
            )
            warmed_feed_cache_count += 1

            search_cache_key = warm_search_cache_for_user(
                member,
                query=effective_query,
                result_type=effective_type,
                payload={
                    "mode": "member-runtime-cache",
                    "member_username": seed.username,
                    "query": effective_query,
                    "result_type": effective_type,
                },
            )
            warmed_search_cache_count += 1

            reservation = reserve_idempotency_key(
                scope="bootstrap-runtime",
                idempotency_key=f"{seed.username}-warmup",
                owner=member,
                request_fingerprint="bootstrap-runtime",
            )
            if reservation["outcome"] == "reserved":
                reserved_idempotency_count += 1
                finalize_idempotency_key(
                    scope="bootstrap-runtime",
                    idempotency_key=f"{seed.username}-warmup",
                    status_code=200,
                    response_payload={
                        "ok": True,
                        "member_username": seed.username,
                        "feed_cache_key": feed_cache_key,
                        "search_cache_key": search_cache_key,
                    },
                )
            elif reservation["outcome"] == "duplicate":
                duplicate_idempotency_count += 1
            else:
                skipped_count += 1

            task_envelope = queue_runtime_task(
                task_name="runtime.bootstrap.warmup",
                queue_name="runtime-maintenance",
                payload={
                    "member_username": seed.username,
                    "feed_cache_key": feed_cache_key,
                    "search_cache_key": search_cache_key,
                },
            )
            queued_task_count += 1

            self._vprint(
                verbose_enabled,
                (
                    "Seeded member=@{username}; feed_key={feed_key}; search_key={search_key}; "
                    "idempotency={idempotency_outcome}; task_id={task_id}; queue_mode={queue_mode}"
                ).format(
                    username=seed.username,
                    feed_key=feed_cache_key,
                    search_key=search_cache_key,
                    idempotency_outcome=reservation["outcome"],
                    task_id=task_envelope["task_id"],
                    queue_mode=task_envelope["mode"],
                ),
            )

        invocation_count = increment_runtime_counter("runtime.bootstrap.invocations", amount=1)
        _counter_row, _snapshot_outcome = snapshot_runtime_counter("runtime.bootstrap.invocations")
        counter_snapshots_count += 1
        self._vprint(
            verbose_enabled,
            f"runtime.bootstrap.invocations counter={invocation_count}; snapshot_written=true",
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Runtime bootstrap complete. "
                f"created_members={created_members_count}, "
                f"warmed_feed_cache={warmed_feed_cache_count}, "
                f"warmed_search_cache={warmed_search_cache_count}, "
                f"reserved_idempotency={reserved_idempotency_count}, "
                f"duplicate_idempotency={duplicate_idempotency_count}, "
                f"queued_tasks={queued_task_count}, "
                f"counter_snapshots={counter_snapshots_count}, "
                f"skipped={skipped_count}"
            )
        )
