from __future__ import annotations

from typing import Any, cast

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.management.base import BaseCommand, CommandParser

from search.models import SearchPayload, build_search_payload_for_user, normalize_search_result_type

UserModel = get_user_model()


class Command(BaseCommand):
    help = "Preview and validate search defaults/results for guest and member flows."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--member-username",
            default="mei",
            help="Member account used for personalized search preview.",
        )
        parser.add_argument(
            "--create-missing-member",
            action="store_true",
            help="Create --member-username if it does not exist.",
        )
        parser.add_argument(
            "--demo-password",
            default="TapneDemoPass!123",
            help="Password used when --create-missing-member creates a user.",
        )
        parser.add_argument(
            "--query",
            default="",
            help="Optional query string used for both guest/member payload previews.",
        )
        parser.add_argument(
            "--type",
            dest="result_type",
            default="all",
            help="Result type filter: all, trips, users, blogs.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=3,
            help="Maximum rows shown per section in preview output.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print detailed ranking previews.",
        )

    def _vprint(self, verbose_enabled: bool, message: str) -> None:
        if verbose_enabled:
            self.stdout.write(f"[search][verbose] {message}")

    def _titles_for(self, payload: SearchPayload, key: str, field: str) -> str:
        rows = cast(list[dict[str, object]], payload[key])
        titles = [str(row.get(field, "")).strip() for row in rows]
        clean_titles = [title for title in titles if title]
        if not clean_titles:
            return "none"
        return ", ".join(clean_titles)

    def _print_payload_summary(self, label: str, payload: SearchPayload) -> None:
        self.stdout.write(
            (
                f"{label}: mode={payload['mode']}; reason={payload['reason']}; "
                f"counts trips={len(payload['trips'])}, profiles={len(payload['profiles'])}, blogs={len(payload['blogs'])}"
            )
        )

    def _print_payload_verbose(self, label: str, payload: SearchPayload) -> None:
        self._vprint(
            True,
            (
                f"{label} trips => {self._titles_for(payload, 'trips', 'title')}; "
                f"profiles => {self._titles_for(payload, 'profiles', 'username')}; "
                f"blogs => {self._titles_for(payload, 'blogs', 'title')}"
            ),
        )

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        verbose_enabled = bool(options.get("verbose"))
        query = str(options.get("query") or "").strip()
        requested_result_type = str(options.get("result_type") or "all")
        normalized_result_type = normalize_search_result_type(requested_result_type)
        limit = max(1, int(options.get("limit") or 3))
        member_username = str(options.get("member_username") or "").strip()
        create_missing_member = bool(options.get("create_missing_member"))
        demo_password = str(options.get("demo_password") or "TapneDemoPass!123")

        self.stdout.write("Bootstrapping search preview records...")
        self._vprint(
            verbose_enabled,
            (
                "query='{query}', requested_type='{requested}', normalized_type='{normalized}', limit={limit}"
                .format(
                    query=query,
                    requested=requested_result_type,
                    normalized=normalized_result_type,
                    limit=limit,
                )
            ),
        )

        if requested_result_type.strip().lower() != normalized_result_type:
            self._vprint(
                verbose_enabled,
                f"Unsupported result type '{requested_result_type}' detected; using 'all'.",
            )

        guest_payload = build_search_payload_for_user(
            AnonymousUser(),
            query=query,
            result_type=normalized_result_type,
            limit_per_section=limit,
        )
        self._print_payload_summary("Guest preview", guest_payload)
        if verbose_enabled:
            self._print_payload_verbose("Guest preview", guest_payload)

        if member_username:
            member_user = cast(Any | None, UserModel.objects.filter(username__iexact=member_username).first())
            if member_user is None and create_missing_member:
                member_user = UserModel.objects.create_user(
                    username=member_username,
                    email=f"{member_username}@tapne.local",
                    password=demo_password,
                )
                self._vprint(verbose_enabled, f"Created missing member @{member_username}")

            if member_user is None:
                self.stdout.write(
                    self.style.WARNING(
                        (
                            f"Skipped member preview for @{member_username}; account not found. "
                            "Use --create-missing-member to create it."
                        )
                    )
                )
            else:
                member_payload = build_search_payload_for_user(
                    member_user,
                    query=query,
                    result_type=normalized_result_type,
                    limit_per_section=limit,
                )
                self._print_payload_summary(f"Member preview (@{member_user.username})", member_payload)
                if verbose_enabled:
                    self._print_payload_verbose(f"Member preview (@{member_user.username})", member_payload)

        self.stdout.write(
            self.style.SUCCESS(
                "Search bootstrap complete. "
                f"query='{query}', result_type='{normalized_result_type}', limit={limit}"
            )
        )
