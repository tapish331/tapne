#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


ROOT_REQUIRED_MARKERS: dict[str, str] = {
    "inline_runtime_attr": 'data-tapne-runtime="inline-config"',
    "inline_runtime_payload": "window.__TAPNE_FRONTEND_CONFIG__",
    "brand_tokens": "frontend-brand/tokens.css",
    "brand_overrides": "frontend-brand/overrides.css",
}

ROOT_FORBIDDEN_MARKERS: dict[str, str] = {
    "external_runtime_dependency": "frontend-runtime.js",
}

HTML_ROUTE_PATHS: tuple[str, ...] = ("/", "/trips", "/blogs")


@dataclass(frozen=True)
class HttpResult:
    url: str
    status: int
    content_type: str
    body: str


JsonObject = dict[str, object]


def _as_json_object(value: object) -> JsonObject | None:
    if not isinstance(value, dict):
        return None

    normalized: JsonObject = {}
    for raw_key, raw_value in cast(dict[object, object], value).items():
        normalized[str(raw_key)] = raw_value
    return normalized


def _as_object_list(value: object) -> list[object] | None:
    if not isinstance(value, list):
        return None
    return cast(list[object], value)


def _get_json_object(payload: JsonObject, key: str) -> JsonObject | None:
    return _as_json_object(payload.get(key))


def _get_object_list(payload: JsonObject, key: str) -> list[object] | None:
    return _as_object_list(payload.get(key))


def _fetch_text(url: str, *, timeout: int) -> HttpResult:
    request = Request(
        url,
        headers={
            "User-Agent": "tapne-cutover-verifier/1.0",
            "Accept": "text/html,application/json,text/plain,*/*",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            content_type = str(response.headers.get("Content-Type", "") or "")
            charset = response.headers.get_content_charset() or "utf-8"
            body = raw.decode(charset, errors="replace")
            return HttpResult(
                url=url,
                status=int(getattr(response, "status", 200)),
                content_type=content_type,
                body=body,
            )
    except HTTPError as exc:
        raw = exc.read()
        content_type = str(exc.headers.get("Content-Type", "") or "")
        charset = exc.headers.get_content_charset() or "utf-8"
        body = raw.decode(charset, errors="replace")
        return HttpResult(url=url, status=int(exc.code), content_type=content_type, body=body)
    except URLError as exc:
        raise SystemExit(f"Request failed for {url}: {exc}") from exc


def _load_json(url: str, *, timeout: int) -> tuple[HttpResult, JsonObject]:
    result = _fetch_text(url, timeout=timeout)
    try:
        payload_obj: object = json.loads(result.body)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Expected JSON from {url} but could not parse it: {exc}") from exc
    payload = _as_json_object(payload_obj)
    if payload is None:
        raise SystemExit(f"Expected JSON object from {url}, got {type(payload_obj).__name__}")
    return result, payload


def _print_ok(message: str) -> None:
    print(f"[OK] {message}")


def _print_fail(message: str) -> None:
    print(f"[FAIL] {message}")


def _collect_asset_paths(index_html: str) -> list[str]:
    matches = re.findall(r"""(?:src|href)=["'](/assets/[^"']+)["']""", index_html)
    ordered: list[str] = []
    seen: set[str] = set()
    for match in matches:
        if match in seen:
            continue
        seen.add(match)
        ordered.append(match)
    return ordered


def _expect_html_route(base_url: str, path: str, *, timeout: int, failures: list[str]) -> HttpResult:
    route_url = urljoin(base_url, path)
    result = _fetch_text(route_url, timeout=timeout)
    if result.status != 200:
        failures.append(f"HTML route returned {result.status}: {route_url}")
    elif "text/html" not in result.content_type.lower():
        failures.append(f"HTML route content type is not HTML for {route_url}: {result.content_type}")
    return result


def verify_live_cutover(base_url: str, *, timeout: int) -> int:
    failures: list[str] = []

    route_results: dict[str, HttpResult] = {
        path: _expect_html_route(base_url, path, timeout=timeout, failures=failures)
        for path in HTML_ROUTE_PATHS
    }
    root_result = route_results["/"]

    for key, marker in ROOT_REQUIRED_MARKERS.items():
        if marker not in root_result.body:
            failures.append(f"Root HTML missing required marker '{key}': {marker}")

    for key, marker in ROOT_FORBIDDEN_MARKERS.items():
        if marker in root_result.body:
            failures.append(f"Root HTML still contains forbidden marker '{key}': {marker}")

    if root_result.body.count(ROOT_REQUIRED_MARKERS["brand_tokens"]) != 1:
        failures.append("Root HTML does not contain exactly one frontend brand tokens reference")
    if root_result.body.count(ROOT_REQUIRED_MARKERS["brand_overrides"]) != 1:
        failures.append("Root HTML does not contain exactly one frontend brand overrides reference")
    if root_result.body.count(ROOT_REQUIRED_MARKERS["inline_runtime_attr"]) != 1:
        failures.append("Root HTML does not contain exactly one inline runtime marker")

    for asset_path in _collect_asset_paths(root_result.body)[:4]:
        asset_url = urljoin(base_url, asset_path)
        asset_result = _fetch_text(asset_url, timeout=timeout)
        if asset_result.status != 200:
            failures.append(f"Frontend asset returned {asset_result.status}: {asset_url}")

    health_result, health_payload = _load_json(urljoin(base_url, "/runtime/health/"), timeout=timeout)
    if health_result.status != 200:
        failures.append(f"Health endpoint returned {health_result.status}")
    if not isinstance(health_payload.get("checked_at"), str):
        failures.append("Health endpoint payload is missing checked_at timestamp")
    if not isinstance(health_payload.get("cache_ok"), bool):
        failures.append("Health endpoint payload is missing boolean cache_ok")

    session_result, session_payload = _load_json(urljoin(base_url, "/frontend-api/session/"), timeout=timeout)
    if session_result.status != 200:
        failures.append(f"Session endpoint returned {session_result.status}")
    if session_payload.get("ok") is not True:
        failures.append("Session endpoint did not return ok=true")

    runtime_payload = _get_json_object(session_payload, "runtime")
    if runtime_payload is None:
        failures.append("Session endpoint payload is missing runtime object")
    else:
        api_payload = _get_json_object(runtime_payload, "api")
        if api_payload is None:
            failures.append("Runtime payload is missing api object")
        elif api_payload.get("base") != "/frontend-api":
            failures.append("Runtime api.base is not '/frontend-api'")

        if runtime_payload.get("frontend_enabled") is not True:
            failures.append("Runtime payload does not report frontend_enabled=true")
        if runtime_payload.get("live_data_required") is not True:
            failures.append("Runtime payload does not report live_data_required=true")

    home_result, home_payload = _load_json(urljoin(base_url, "/frontend-api/home/"), timeout=timeout)
    if home_result.status != 200:
        failures.append(f"Home API returned {home_result.status}")
    if home_payload.get("ok") is not True:
        failures.append("Home API did not return ok=true")

    trips_result, trips_payload = _load_json(urljoin(base_url, "/frontend-api/trips/"), timeout=timeout)
    if trips_result.status != 200:
        failures.append(f"Trips API returned {trips_result.status}")
    if trips_payload.get("ok") is not True:
        failures.append("Trips API did not return ok=true")
    if trips_payload.get("source") != "live-db":
        failures.append("Trips API does not report source=live-db")

    blogs_result, blogs_payload = _load_json(urljoin(base_url, "/frontend-api/blogs/"), timeout=timeout)
    if blogs_result.status != 200:
        failures.append(f"Blogs API returned {blogs_result.status}")
    if blogs_payload.get("ok") is not True:
        failures.append("Blogs API did not return ok=true")
    if blogs_payload.get("source") != "live-db":
        failures.append("Blogs API does not report source=live-db")

    trips_value = _get_object_list(trips_payload, "trips")
    if trips_value:
        first_trip = trips_value[0]
        trip_payload = _as_json_object(first_trip)
        if trip_payload is not None:
            trip_url = str(trip_payload.get("url", "") or "").strip()
            if trip_url:
                _expect_html_route(base_url, trip_url, timeout=timeout, failures=failures)

    blogs_value = _get_object_list(blogs_payload, "blogs")
    if blogs_value:
        first_blog = blogs_value[0]
        blog_payload = _as_json_object(first_blog)
        if blog_payload is not None:
            blog_url = str(blog_payload.get("url", "") or "").strip()
            if blog_url:
                _expect_html_route(base_url, blog_url, timeout=timeout, failures=failures)

    print("Lovable live cutover verification")
    print("")
    print(f"base_url: {base_url}")
    print("")

    if failures:
        for failure in failures:
            _print_fail(failure)
        return 1

    _print_ok("Root HTML serves the SPA shell with inline runtime config.")
    _print_ok("No external /frontend-runtime.js dependency remains.")
    _print_ok("Public SPA routes return HTML on direct loads.")
    _print_ok("Frontend assets requested from the live shell return 200.")
    _print_ok("Health endpoint returns 200 with JSON payload.")
    _print_ok("Session endpoint returns live runtime config and same-origin API base.")
    _print_ok("Home, trips, and blogs APIs return real same-origin payloads.")
    _print_ok("Derived public detail routes return HTML on direct loads.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify that the live cutover site serves the hardened Lovable shell and same-origin Django APIs."
    )
    parser.add_argument("--base-url", required=True, help="Base URL to verify, for example https://tapnetravel.com/")
    parser.add_argument("--timeout", type=int, default=20, help="Per-request timeout in seconds.")
    args = parser.parse_args()

    base_url = str(args.base_url or "").strip()
    if not base_url:
        raise SystemExit("--base-url is required")

    return verify_live_cutover(base_url, timeout=max(1, int(args.timeout)))


if __name__ == "__main__":
    sys.exit(main())
