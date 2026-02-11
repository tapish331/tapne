from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    RuntimeCounter,
    RuntimeIdempotencyRecord,
    check_rate_limit,
    feed_cache_key_for_user,
    finalize_idempotency_key,
    get_buffered_runtime_tasks,
    get_cached_payload,
    increment_runtime_counter,
    queue_runtime_task,
    reserve_idempotency_key,
    search_cache_key_for_user,
    snapshot_runtime_counter,
    warm_feed_cache_for_user,
    warm_search_cache_for_user,
)

UserModel = get_user_model()


class RuntimeUtilityTests(TestCase):
    def setUp(self) -> None:
        self.password = "RuntimePass!123456"
        self.member = UserModel.objects.create_user(
            username="runtime-member",
            email="runtime-member@example.com",
            password=self.password,
        )

    def test_feed_and_search_cache_helpers_warm_and_read_payloads(self) -> None:
        feed_key = warm_feed_cache_for_user(
            self.member,
            payload={"mode": "member", "reason": "runtime test"},
        )
        search_key = warm_search_cache_for_user(
            self.member,
            query="tapne",
            result_type="users",
            payload={"mode": "member", "query": "tapne"},
        )

        self.assertEqual(feed_key, feed_cache_key_for_user(self.member))
        self.assertEqual(
            search_key,
            search_cache_key_for_user(self.member, query="tapne", result_type="users"),
        )
        self.assertIsNotNone(get_cached_payload(feed_key))
        self.assertIsNotNone(get_cached_payload(search_key))

    def test_rate_limit_blocks_after_limit_is_exceeded(self) -> None:
        first = check_rate_limit(
            scope="dm-send",
            identifier=f"user:{self.member.pk}",
            limit=2,
            window_seconds=60,
        )
        second = check_rate_limit(
            scope="dm-send",
            identifier=f"user:{self.member.pk}",
            limit=2,
            window_seconds=60,
        )
        third = check_rate_limit(
            scope="dm-send",
            identifier=f"user:{self.member.pk}",
            limit=2,
            window_seconds=60,
        )

        self.assertTrue(first["allowed"])
        self.assertTrue(second["allowed"])
        self.assertFalse(third["allowed"])
        self.assertEqual(third["outcome"], "blocked")
        self.assertEqual(third["remaining"], 0)

    def test_idempotency_reservation_duplicate_and_finalize_response(self) -> None:
        first = reserve_idempotency_key(
            scope="trip-join",
            idempotency_key="join-123",
            owner=self.member,
            request_fingerprint="trip-join-body-v1",
        )
        self.assertEqual(first["outcome"], "reserved")
        self.assertIsNotNone(first["record_id"])

        row = finalize_idempotency_key(
            scope="trip-join",
            idempotency_key="join-123",
            status_code=201,
            response_payload={"result": "accepted"},
        )
        if row is None:
            self.fail("Expected finalize_idempotency_key to return a row")
        self.assertEqual(row.status_code, 201)

        second = reserve_idempotency_key(
            scope="trip-join",
            idempotency_key="join-123",
            owner=self.member,
            request_fingerprint="trip-join-body-v1",
        )
        self.assertEqual(second["outcome"], "duplicate")
        self.assertEqual(second["existing_status_code"], 201)
        second_payload = second["response_payload"]
        if second_payload is None:
            self.fail("Expected duplicate idempotency response payload to be present")
        self.assertEqual(second_payload["result"], "accepted")

    def test_expired_idempotency_keys_can_be_reserved_again(self) -> None:
        first = reserve_idempotency_key(
            scope="review-create",
            idempotency_key="review-1",
            owner=self.member,
            ttl_seconds=5,
        )
        self.assertEqual(first["outcome"], "reserved")

        row = RuntimeIdempotencyRecord.objects.get(scope="review-create", idempotency_key="review-1")
        row.expires_at = timezone.now() - timedelta(seconds=1)
        row.save(update_fields=["expires_at", "updated_at"])

        second = reserve_idempotency_key(
            scope="review-create",
            idempotency_key="review-1",
            owner=self.member,
            ttl_seconds=5,
        )
        self.assertEqual(second["outcome"], "reserved")

    def test_counter_increment_and_snapshot(self) -> None:
        first = increment_runtime_counter("runtime.tests.counter", amount=2)
        second = increment_runtime_counter("runtime.tests.counter", amount=3)
        self.assertGreaterEqual(first, 2)
        self.assertGreaterEqual(second, 5)

        row, outcome = snapshot_runtime_counter("runtime.tests.counter")
        self.assertIn(outcome, {"created", "updated"})
        self.assertEqual(row.key, "runtime.tests.counter")
        self.assertGreaterEqual(row.value, 5)

        row_again, outcome_again = snapshot_runtime_counter("runtime.tests.counter")
        self.assertEqual(row_again.pk, row.pk)
        self.assertEqual(outcome_again, "updated")

    def test_queue_runtime_task_buffers_task_envelopes(self) -> None:
        envelope = queue_runtime_task(
            task_name="runtime.tests.sample-task",
            queue_name="runtime-tests",
            payload={"hello": "world"},
        )
        tasks = get_buffered_runtime_tasks(queue_name="runtime-tests", limit=10)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_id"], envelope["task_id"])
        self.assertEqual(tasks[0]["task_name"], "runtime.tests.sample-task")


class RuntimeViewsTests(TestCase):
    def setUp(self) -> None:
        self.password = "RuntimeViewPass!123456"
        self.member = UserModel.objects.create_user(
            username="runtime-view-member",
            email="runtime-view-member@example.com",
            password=self.password,
        )

    def test_runtime_health_endpoint_returns_snapshot(self) -> None:
        response = self.client.get(reverse("runtime:health"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("cache_ok", payload)
        self.assertIn("redis_configured", payload)
        self.assertIn("broker_configured", payload)

    def test_runtime_health_verbose_query_prints_debug_lines(self) -> None:
        with patch("builtins.print") as mock_print:
            response = self.client.get(f"{reverse('runtime:health')}?verbose=1")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(mock_print.call_count, 1)
        printed_lines = "\n".join(str(args[0]) for args, _kwargs in mock_print.call_args_list)
        self.assertIn("[runtime][verbose]", printed_lines)

    def test_runtime_cache_preview_requires_login(self) -> None:
        response = self.client.get(reverse("runtime:cache-preview"))
        expected_redirect = f"{reverse('accounts:login')}?next={reverse('runtime:cache-preview')}"
        self.assertRedirects(response, expected_redirect, fetch_redirect_response=False)

    def test_runtime_cache_preview_reports_hits_for_warmed_member_cache(self) -> None:
        self.client.login(username=self.member.username, password=self.password)
        warm_feed_cache_for_user(
            self.member,
            payload={"mode": "member", "reason": "view test"},
        )
        warm_search_cache_for_user(
            self.member,
            query="tapne",
            result_type="all",
            payload={"mode": "member", "query": "tapne"},
        )

        response = self.client.get(
            f"{reverse('runtime:cache-preview')}?q=tapne&type=all"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["feed_cache_hit"])
        self.assertTrue(payload["search_cache_hit"])


class RuntimeBootstrapCommandTests(TestCase):
    def test_bootstrap_runtime_creates_expected_runtime_artifacts_with_verbose_output(self) -> None:
        stdout = StringIO()
        call_command(
            "bootstrap_runtime",
            "--create-missing-members",
            "--verbose",
            stdout=stdout,
        )
        output = stdout.getvalue()

        self.assertIn("[runtime][verbose]", output)
        self.assertIn("Runtime bootstrap complete", output)
        self.assertTrue(UserModel.objects.filter(username="mei").exists())
        self.assertTrue(RuntimeIdempotencyRecord.objects.filter(scope="bootstrap-runtime").exists())
        self.assertGreaterEqual(RuntimeCounter.objects.count(), 1)
