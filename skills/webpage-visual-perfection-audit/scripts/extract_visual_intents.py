#!/usr/bin/env python3
"""Stage 3 stub: extract visual intent contracts from code and crawl output.

This script is intentionally conservative and deterministic:
1. Load crawled pages from pages.json.
2. Generate stable route-level intent contracts.
3. Attach source evidence (file + line) from templates/CSS/JS.
4. Emit machine-readable and reviewer-friendly artifacts.

It is a stub. The catalog is useful immediately, but should be expanded
for full semantic coverage over time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qsl, urlencode, urlsplit


SUPPORTED_INTENT_TYPES = [
    "carousel_horizontal",
    "stack_on_breakpoint",
    "no_card_overlap",
    "card_size_balance",
    "cta_uniqueness_within_section",
    "section_spacing_rhythm",
    "header_token_consistency",
    "footer_readability_mobile",
    "search_chrome_contrast_dark",
]

NON_HTML_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".css",
    ".js",
    ".json",
    ".xml",
    ".txt",
    ".pdf",
    ".mp4",
    ".webm",
    ".mov",
    ".zip",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage 3 stub: extract visual intent contracts from pages and source."
    )
    parser.add_argument(
        "--pages-json",
        required=True,
        help="Path to pages.json produced by crawl_and_capture.py.",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root for source evidence lookups.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where intent artifacts will be written.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if minimum Stage 3 acceptance checks do not pass.",
    )
    return parser.parse_args()


def normalize_route(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    if not parsed.query:
        return path
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)), doseq=True)
    return f"{path}?{query}"


def is_probable_html_url(url: str) -> bool:
    path = urlsplit(url).path.lower()
    for suffix in NON_HTML_EXTENSIONS:
        if path.endswith(suffix):
            return False
    return True


def slugify_token(value: str) -> str:
    token = "".join(ch if ch.isalnum() else "-" for ch in value.lower()).strip("-")
    while "--" in token:
        token = token.replace("--", "-")
    return token or "x"


def stable_intent_id(route: str, component_label: str, intent_type: str) -> str:
    route_slug = slugify_token(route if route else "/")
    component_slug = slugify_token(component_label)[:24]
    digest = hashlib.sha1(
        f"{route}|{component_label}|{intent_type}".encode("utf-8")
    ).hexdigest()[:8]
    return f"INT-{route_slug}-{component_slug}-{intent_type}-{digest}"


def load_lines(repo_root: Path, rel_path: str, cache: dict[str, list[str]]) -> list[str]:
    if rel_path in cache:
        return cache[rel_path]
    path = repo_root / rel_path
    if not path.exists():
        cache[rel_path] = []
        return cache[rel_path]
    cache[rel_path] = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return cache[rel_path]


def as_json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return {}


def find_line_for_pattern(lines: list[str], pattern: str) -> int | None:
    for idx, line in enumerate(lines, start=1):
        if pattern in line:
            return idx
    return None


def build_evidence(
    repo_root: Path,
    signals: list[tuple[str, str]],
    cache: dict[str, list[str]],
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for rel_path, pattern in signals:
        lines = load_lines(repo_root, rel_path, cache)
        line_number = find_line_for_pattern(lines, pattern)
        if line_number is None:
            continue
        evidence.append({"file": rel_path.replace("\\", "/"), "line": line_number})
    return evidence


def base_intent_blueprints() -> list[dict[str, Any]]:
    return [
        {
            "component_label": "Global Header",
            "intent_type": "header_token_consistency",
            "locator_css": ".site-header",
            "expected_rule": (
                "Header shell, typography, and icon controls remain token-consistent "
                "across route templates."
            ),
            "thresholds": {
                "nav_font_px_min": 13.0,
                "nav_font_px_max": 16.0,
                "header_min_height_px": 64.0,
            },
            "breakpoints": [1440, 1280, 1024, 900, 768, 600, 390],
            "interaction_profile": "none",
            "confidence": 0.88,
            "severity_if_broken": "Medium",
            "evidence_signals": [
                ("templates/base.html", '<header class="site-header'),
                ("static/css/tapne.css", ".site-header {"),
            ],
        },
        {
            "component_label": "Global Footer",
            "intent_type": "footer_readability_mobile",
            "locator_css": ".site-footer",
            "expected_rule": (
                "Footer typography remains secondary but comfortably readable on mobile."
            ),
            "thresholds": {
                "max_mobile_width_px": 768,
                "min_link_font_px": 14.0,
                "min_copy_font_px": 13.5,
            },
            "breakpoints": [768, 600, 390],
            "interaction_profile": "none",
            "confidence": 0.9,
            "severity_if_broken": "Low",
            "evidence_signals": [
                ("templates/base.html", '<footer class="site-footer'),
                ("static/css/tapne.css", ".site-footer {"),
            ],
        },
        {
            "component_label": "Global Search",
            "intent_type": "search_chrome_contrast_dark",
            "locator_css": ".lv-search-shell",
            "expected_rule": (
                "Search shell and placeholder remain visually distinct in dark theme, "
                "with visible focus affordance."
            ),
            "thresholds": {
                "require_focus_ring": True,
                "require_placeholder_bg_distinction": True,
            },
            "breakpoints": [1440, 1024, 768, 390],
            "interaction_profile": "none",
            "confidence": 0.9,
            "severity_if_broken": "Low",
            "evidence_signals": [
                ("templates/base.html", "lv-search-shell"),
                ("static/css/lovable-parity.css", ".lv-search-shell {"),
                ("static/css/tapne.css", "input::placeholder"),
            ],
        },
    ]


def home_intent_blueprints() -> list[dict[str, Any]]:
    return [
        {
            "component_label": "Explore Trips",
            "intent_type": "carousel_horizontal",
            "locator_css": ".lovable-card-carousel[aria-label='Explore trips carousel']",
            "expected_rule": "Explore Trips presents horizontally scrollable cards without overlap.",
            "thresholds": {"min_scroll_overflow_px": 16, "max_overlap_ratio": 0.0},
            "breakpoints": [1440, 1280, 1024, 900, 768, 600, 390],
            "interaction_profile": "scroll_x",
            "confidence": 0.95,
            "severity_if_broken": "High",
            "evidence_signals": [
                ("templates/pages/home.html", "Explore trips carousel"),
                ("static/css/lovable-parity.css", ".lovable-card-carousel {"),
            ],
        },
        {
            "component_label": "Explore Destinations",
            "intent_type": "carousel_horizontal",
            "locator_css": ".lovable-card-carousel[aria-label='Destinations carousel']",
            "expected_rule": "Explore Destinations behaves as a horizontal carousel across breakpoints.",
            "thresholds": {"min_scroll_overflow_px": 16, "max_overlap_ratio": 0.0},
            "breakpoints": [1440, 1280, 1024, 900, 768, 600, 390],
            "interaction_profile": "scroll_x",
            "confidence": 0.95,
            "severity_if_broken": "High",
            "evidence_signals": [
                ("templates/pages/home.html", "Destinations carousel"),
                ("static/css/lovable-parity.css", ".lovable-card-carousel {"),
            ],
        },
        {
            "component_label": "From the Community",
            "intent_type": "carousel_horizontal",
            "locator_css": ".lovable-card-carousel[aria-label='Community blogs carousel']",
            "expected_rule": "Community feed cards remain a horizontal carousel with stable item sizing.",
            "thresholds": {"min_scroll_overflow_px": 16, "max_overlap_ratio": 0.0},
            "breakpoints": [1440, 1280, 1024, 900, 768, 600, 390],
            "interaction_profile": "scroll_x",
            "confidence": 0.95,
            "severity_if_broken": "High",
            "evidence_signals": [
                ("templates/pages/home.html", "Community blogs carousel"),
                ("static/css/lovable-parity.css", ".lovable-horizontal-carousel {"),
            ],
        },
        {
            "component_label": "Explore Destinations Card Sizing",
            "intent_type": "card_size_balance",
            "locator_css": ".lovable-card-carousel[aria-label='Destinations carousel']",
            "expected_rule": "Destination cards keep balanced widths and do not dominate section composition.",
            "thresholds": {"max_width_ratio": 1.8, "max_width_px_desktop": 420},
            "breakpoints": [1440, 1280, 1024, 900, 768, 600, 390],
            "interaction_profile": "none",
            "confidence": 0.9,
            "severity_if_broken": "Medium",
            "evidence_signals": [
                ("templates/pages/home.html", "Explore Destinations"),
                ("static/css/lovable-parity.css", ".lovable-destination-teaser"),
            ],
        },
        {
            "component_label": "Home Card Overlap Prevention",
            "intent_type": "no_card_overlap",
            "locator_css": ".lovable-home-shell",
            "expected_rule": "Card sections do not overlap at any supported breakpoint.",
            "thresholds": {"max_overlap_ratio": 0.0},
            "breakpoints": [1440, 1280, 1024, 900, 768, 600, 390],
            "interaction_profile": "resize_stepdown",
            "confidence": 0.92,
            "severity_if_broken": "High",
            "evidence_signals": [
                ("templates/pages/home.html", '<div class="lovable-home-shell">'),
                ("static/css/lovable-parity.css", ".lovable-home-shell"),
            ],
        },
        {
            "component_label": "Home Breakpoint Stacking",
            "intent_type": "stack_on_breakpoint",
            "locator_css": ".lovable-card-carousel",
            "expected_rule": "Home cards stack/reflow cleanly with no collisions at narrow widths.",
            "thresholds": {"stack_at_or_below_px": 768, "max_overlap_ratio": 0.0},
            "breakpoints": [768, 600, 390],
            "interaction_profile": "resize_stepdown",
            "confidence": 0.88,
            "severity_if_broken": "High",
            "evidence_signals": [
                ("templates/pages/home.html", "lovable-card-carousel"),
                ("static/css/lovable-parity.css", "@media (max-width: 760px)"),
            ],
        },
        {
            "component_label": "Community CTA Uniqueness",
            "intent_type": "cta_uniqueness_within_section",
            "locator_css": "section[data-home-section='community']",
            "expected_rule": "Community section exposes one primary View All CTA per viewport context.",
            "thresholds": {"max_matching_cta": 1, "match_text_regex": "(?i)view\\s+all"},
            "breakpoints": [1440, 1024, 768, 390],
            "interaction_profile": "none",
            "confidence": 0.83,
            "severity_if_broken": "Medium",
            "evidence_signals": [
                ("templates/pages/home.html", 'data-home-section="community"'),
                ("templates/pages/home.html", "View all blogs"),
            ],
        },
        {
            "component_label": "Home Section Rhythm",
            "intent_type": "section_spacing_rhythm",
            "locator_css": ".lovable-home-shell",
            "expected_rule": "Section spacing is even and free from random blank vertical gaps.",
            "thresholds": {"max_gap_variance_px": 18},
            "breakpoints": [1440, 1024, 768, 390],
            "interaction_profile": "none",
            "confidence": 0.82,
            "severity_if_broken": "Medium",
            "evidence_signals": [
                ("templates/pages/home.html", "lovable-home-shell"),
                ("static/css/lovable-parity.css", ".lovable-home-shell"),
            ],
        },
    ]


def instantiate_blueprint(
    blueprint: dict[str, Any],
    route: str,
    route_url: str,
    repo_root: Path,
    cache: dict[str, list[str]],
) -> dict[str, Any]:
    component_label = blueprint["component_label"]
    intent_type = blueprint["intent_type"]
    if intent_type not in SUPPORTED_INTENT_TYPES:
        raise ValueError(f"Unsupported intent_type: {intent_type}")
    evidence = build_evidence(repo_root, blueprint["evidence_signals"], cache)
    return {
        "intent_id": stable_intent_id(route, component_label, intent_type),
        "route": route,
        "route_url": route_url,
        "component_label": component_label,
        "intent_type": intent_type,
        "locator_css": blueprint["locator_css"],
        "expected_rule": blueprint["expected_rule"],
        "thresholds": blueprint["thresholds"],
        "breakpoints": blueprint["breakpoints"],
        "interaction_profile": blueprint["interaction_profile"],
        "confidence": float(blueprint["confidence"]),
        "severity_if_broken": blueprint["severity_if_broken"],
        "evidence": evidence,
    }


def write_intent_catalog_md(output_path: Path, payload: dict[str, Any]) -> None:
    intents = payload["intents"]
    counts_by_type: dict[str, int] = {}
    counts_by_route: dict[str, int] = {}
    for intent in intents:
        counts_by_type[intent["intent_type"]] = counts_by_type.get(intent["intent_type"], 0) + 1
        counts_by_route[intent["route"]] = counts_by_route.get(intent["route"], 0) + 1

    lines: list[str] = []
    lines.append("# Intent Catalog (Stage 3 Stub)")
    lines.append("")
    lines.append(f"- Generated at UTC: `{payload['generated_at_utc']}`")
    lines.append(f"- Source pages.json: `{payload['source_pages_json']}`")
    lines.append(f"- Route count with intents: `{len(counts_by_route)}`")
    lines.append(f"- Intent count: `{payload['intent_count']}`")
    lines.append("")
    lines.append("## Acceptance Checks")
    for check in payload["acceptance_checks"]:
        marker = "PASS" if check["pass"] else "FAIL"
        lines.append(f"- `{marker}` {check['name']}: {check['details']}")
    lines.append("")
    lines.append("## Intent Types")
    for intent_type in sorted(counts_by_type):
        lines.append(f"- `{intent_type}`: {counts_by_type[intent_type]}")
    lines.append("")
    lines.append("## Routes")
    for route in sorted(counts_by_route):
        lines.append(f"- `{route}`: {counts_by_route[route]} intents")
    lines.append("")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_evidence_tsv(output_path: Path, intents: list[dict[str, Any]]) -> None:
    lines = ["intent_id\troute\tintent_type\tfile\tline"]
    for intent in intents:
        if not intent["evidence"]:
            lines.append(
                f"{intent['intent_id']}\t{intent['route']}\t{intent['intent_type']}\tMISSING\t"
            )
            continue
        for item in intent["evidence"]:
            lines.append(
                f"{intent['intent_id']}\t{intent['route']}\t{intent['intent_type']}\t"
                f"{item['file']}\t{item['line']}"
            )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    pages_json_path = Path(args.pages_json).resolve()
    repo_root = Path(args.repo_root).resolve()
    output_dir = Path(args.output_dir).resolve()

    if not pages_json_path.exists():
        print(f"[error] --pages-json not found: {pages_json_path}")
        return 1
    if not repo_root.exists():
        print(f"[error] --repo-root not found: {repo_root}")
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    raw_payload = json.loads(pages_json_path.read_text(encoding="utf-8"))
    payload_obj = as_json_dict(raw_payload)
    pages_value: object = payload_obj.get("pages")
    if not isinstance(pages_value, list):
        print("[error] pages.json does not contain a `pages` list.")
        return 1
    pages: list[dict[str, Any]] = []
    for item in cast(list[object], pages_value):
        if isinstance(item, dict):
            pages.append(cast(dict[str, Any], item))

    ok_pages = [page for page in pages if page.get("crawl_status") == "ok" and page.get("url")]
    html_pages = [page for page in ok_pages if is_probable_html_url(str(page.get("url", "")))]
    line_cache: dict[str, list[str]] = {}
    intents: list[dict[str, Any]] = []
    intents_per_route: dict[str, int] = {}

    for page in html_pages:
        route_url = str(page["url"])
        route = normalize_route(route_url)
        page_intents: list[dict[str, Any]] = []

        for blueprint in base_intent_blueprints():
            page_intents.append(
                instantiate_blueprint(blueprint, route, route_url, repo_root, line_cache)
            )

        if route == "/":
            for blueprint in home_intent_blueprints():
                page_intents.append(
                    instantiate_blueprint(blueprint, route, route_url, repo_root, line_cache)
                )

        intents.extend(page_intents)
        intents_per_route[route] = intents_per_route.get(route, 0) + len(page_intents)

    unique_intent_ids = {intent["intent_id"] for intent in intents}
    min_intents_per_ok_page = min(intents_per_route.values(), default=0)
    home_intent_types = {str(intent["intent_type"]) for intent in intents if intent["route"] == "/"}

    acceptance_checks: list[dict[str, Any]] = [
        {
            "name": "ok-pages-have-minimum-intents",
            "pass": min_intents_per_ok_page >= 2 if html_pages else False,
            "details": f"minimum intents per html ok page = {min_intents_per_ok_page}",
        },
        {
            "name": "every-intent-has-evidence",
            "pass": all(bool(intent["evidence"]) for intent in intents),
            "details": (
                f"{sum(1 for intent in intents if intent['evidence'])}/{len(intents)} intents "
                "contain source evidence"
            ),
        },
        {
            "name": "intent-ids-are-unique",
            "pass": len(unique_intent_ids) == len(intents),
            "details": f"{len(unique_intent_ids)} unique IDs for {len(intents)} intents",
        },
        {
            "name": "home-route-core-intents-present",
            "pass": all(
                intent_type in home_intent_types
                for intent_type in {
                    "carousel_horizontal",
                    "no_card_overlap",
                    "card_size_balance",
                    "stack_on_breakpoint",
                    "cta_uniqueness_within_section",
                }
            ),
            "details": "home route includes carousel/overlap/size/stack/cta intents",
        },
    ]

    payload: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_pages_json": str(pages_json_path),
        "repo_root": str(repo_root),
        "strict_mode": bool(args.strict),
        "page_count": len(pages),
        "ok_page_count": len(ok_pages),
        "html_ok_page_count": len(html_pages),
        "intent_count": len(intents),
        "supported_intent_types": SUPPORTED_INTENT_TYPES,
        "coverage": {
            "routes_with_intents": len(intents_per_route),
            "minimum_intents_per_ok_page": min_intents_per_ok_page,
        },
        "acceptance_checks": acceptance_checks,
        "intents": intents,
    }

    catalog_json = output_dir / "intent_catalog.json"
    catalog_md = output_dir / "intent_catalog.md"
    evidence_tsv = output_dir / "intent_evidence_index.tsv"

    catalog_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_intent_catalog_md(catalog_md, payload)
    write_evidence_tsv(evidence_tsv, intents)

    print(f"[done] Intent catalog: {catalog_json}")
    print(f"[done] Intent summary: {catalog_md}")
    print(f"[done] Evidence index: {evidence_tsv}")

    if args.strict and not all(check["pass"] for check in acceptance_checks):
        print("[error] Strict mode failed: one or more acceptance checks did not pass.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
