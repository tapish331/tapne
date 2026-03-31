#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Stage 4 stub: validate visual intents against rendered webpages.

This script executes conformance checks from intent_catalog.json against
real browser renders. It focuses on deterministic checks with measurable output.

It is a stub. It supports key intent types and is designed to be extended.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, cast
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit

PlaywrightFactory = Callable[[], Any]

PlaywrightError: type[Exception] = Exception
async_playwright: PlaywrightFactory | None = None
playwright_import_error: Exception | None = None
playwright_module: object | None = None
try:
    playwright_module = importlib.import_module("playwright.async_api")
except ImportError as exc:  # pragma: no cover - environment dependent
    playwright_import_error = exc
else:
    imported_playwright_error: object = getattr(playwright_module, "Error", Exception)
    imported_async_playwright: object = getattr(playwright_module, "async_playwright", None)
    if isinstance(imported_playwright_error, type) and issubclass(imported_playwright_error, Exception):
        PlaywrightError = imported_playwright_error
    if callable(imported_async_playwright):
        async_playwright = cast(PlaywrightFactory, imported_async_playwright)


MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 "
    "Safari/604.1"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage 4 stub: validate visual intents against rendered pages."
    )
    parser.add_argument("--base-url", required=True, help="Base URL for route resolution.")
    parser.add_argument(
        "--pages-json",
        required=True,
        help="pages.json produced by crawl_and_capture.py.",
    )
    parser.add_argument(
        "--intent-catalog",
        required=True,
        help="intent_catalog.json produced by extract_visual_intents.py.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for conformance artifacts.",
    )
    parser.add_argument(
        "--storage-state",
        default="",
        help="Optional Playwright storage_state JSON for authenticated routes.",
    )
    parser.add_argument(
        "--strict-high-confidence",
        action="store_true",
        help="Fail when confidence>=0.90 and severity High/Critical intent fails.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=45000,
        help="Navigation and action timeout in milliseconds.",
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=900,
        help="Extra wait after network idle for late paints.",
    )
    parser.add_argument(
        "--max-breakpoints-per-intent",
        type=int,
        default=0,
        help="Optional cap for stub runs. 0 means evaluate all declared breakpoints.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in headed mode for debugging.",
    )
    return parser.parse_args()


def normalize_base_url(raw: str) -> str:
    value = raw.strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("--base-url must be a valid http/https URL.")
    return value.rstrip("/")


def normalize_route(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    if not parsed.query:
        return path
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)), doseq=True)
    return f"{path}?{query}"


def slugify(value: str) -> str:
    token = "".join(ch if ch.isalnum() else "-" for ch in value.lower()).strip("-")
    while "--" in token:
        token = token.replace("--", "-")
    return token or "x"


def to_rel(path: Path, base: Path) -> str:
    return path.resolve().relative_to(base.resolve()).as_posix()


def as_json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return {}


def as_json_dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    raw_items = cast(list[object], value)
    for item in raw_items:
        if isinstance(item, dict):
            items.append(cast(dict[str, Any], item))
    return items


def parse_px(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower()
    if text.endswith("px"):
        text = text[:-2]
    try:
        return float(text)
    except ValueError:
        return None


VALID_JS_REGEX_FLAGS = set("dgimsuy")


def normalize_regex_flags(flags: str) -> str:
    deduped: list[str] = []
    seen: set[str] = set()
    for ch in flags:
        if ch in VALID_JS_REGEX_FLAGS and ch not in seen:
            deduped.append(ch)
            seen.add(ch)
    return "".join(deduped)


def parse_regex_pattern_flags(
    raw_regex: Any,
    default_pattern: str = "view\\s+all",
    default_flags: str = "i",
) -> tuple[str, str]:
    text = str(raw_regex or "").strip()
    if not text:
        return default_pattern, normalize_regex_flags(default_flags) or "i"

    pattern = text
    flags = ""

    # Support JS-style /pattern/flags.
    if text.startswith("/") and text.count("/") >= 2:
        last_slash = text.rfind("/")
        if last_slash > 0:
            pattern = text[1:last_slash]
            flags = text[last_slash + 1 :]

    # Support Python-style inline flags prefix, e.g. (?i)pattern.
    inline_match = re.match(r"^\(\?([a-zA-Z]+)\)", pattern)
    if inline_match:
        inline_flags = inline_match.group(1)
        pattern = pattern[inline_match.end() :]
        flags = inline_flags + flags

    normalized_flags = normalize_regex_flags(default_flags + flags) or "i"
    normalized_pattern = pattern or default_pattern
    return normalized_pattern, normalized_flags


def route_url_for_intent(
    intent: dict[str, Any],
    route_to_url: dict[str, str],
    base_url: str,
) -> str:
    explicit = str(intent.get("route_url", "")).strip()
    if explicit:
        return explicit
    route = str(intent.get("route", "")).strip() or "/"
    if route in route_to_url:
        return route_to_url[route]
    if route.startswith("/"):
        return urljoin(base_url + "/", route.lstrip("/"))
    return urljoin(base_url + "/", route)


async def evaluate_carousel_horizontal(page: Any, selector: str, thresholds: dict[str, Any]) -> dict[str, Any]:
    measured = await page.evaluate(
        """
        (sel) => {
          let root = null;
          try { root = document.querySelector(sel); } catch (err) { root = null; }
          if (!root) {
            return { exists: false };
          }
          const before = root.scrollLeft;
          const clientWidth = root.clientWidth;
          const scrollWidth = root.scrollWidth;
          const delta = Math.max(80, Math.floor(clientWidth * 0.6));
          root.scrollLeft = before + delta;
          const after = root.scrollLeft;
          return {
            exists: true,
            client_width_px: clientWidth,
            scroll_width_px: scrollWidth,
            overflow_px: Math.max(0, scrollWidth - clientWidth),
            before_scroll_left_px: before,
            after_scroll_left_px: after
          };
        }
        """,
        selector,
    )

    if not measured.get("exists"):
        return {"status": "fail", "reason": "selector_not_found", "measured": measured}

    min_overflow = float(thresholds.get("min_scroll_overflow_px", 16))
    overflow = float(measured.get("overflow_px", 0))
    scrolled = float(measured.get("after_scroll_left_px", 0)) > float(
        measured.get("before_scroll_left_px", 0)
    )
    if overflow < min_overflow:
        return {"status": "fail", "reason": "insufficient_overflow", "measured": measured}
    if not scrolled:
        return {"status": "fail", "reason": "scroll_did_not_advance", "measured": measured}
    return {"status": "pass", "reason": "ok", "measured": measured}


async def evaluate_cta_uniqueness(page: Any, selector: str, thresholds: dict[str, Any]) -> dict[str, Any]:
    regex_pattern, regex_flags = parse_regex_pattern_flags(
        thresholds.get("match_text_regex", "(?i)view\\s+all")
    )
    max_matching = int(thresholds.get("max_matching_cta", 1))
    measured = await page.evaluate(
        """
        ({sel, regexPattern, regexFlags}) => {
          let root = null;
          try { root = document.querySelector(sel); } catch (err) { root = null; }
          if (!root) {
            root = document.body;
          }
          let pattern = null;
          try {
            pattern = new RegExp(regexPattern, regexFlags || "i");
          } catch (err) {
            return {
              exists: Boolean(root),
              matching_cta_count: 0,
              labels: [],
              pattern_error: String(err)
            };
          }
          const labels = Array.from(root.querySelectorAll("a,button"))
            .filter((el) => {
              if (!el || typeof el.getBoundingClientRect !== "function") {
                return false;
              }
              if (typeof el.closest === "function" && el.closest("[hidden], [aria-hidden='true']")) {
                return false;
              }
              const style = window.getComputedStyle(el);
              if (!style || style.display === "none" || style.visibility === "hidden") {
                return false;
              }
              if (parseFloat(style.opacity || "1") === 0) {
                return false;
              }
              const rect = el.getBoundingClientRect();
              return rect.width > 1 && rect.height > 1;
            })
            .map((el) => (el.textContent || "").trim())
            .filter((label) => pattern.test(label));
          return {
            exists: Boolean(root),
            visible_candidates: Array.from(root.querySelectorAll("a,button")).length,
            matching_cta_count: labels.length,
            labels: labels.slice(0, 10)
          };
        }
        """,
        {"sel": selector, "regexPattern": regex_pattern, "regexFlags": regex_flags},
    )
    if measured.get("pattern_error"):
        return {"status": "fail", "reason": "invalid_regex_pattern", "measured": measured}
    count = int(measured.get("matching_cta_count", 0))
    if count > max_matching:
        return {"status": "fail", "reason": "duplicate_cta_detected", "measured": measured}
    return {"status": "pass", "reason": "ok", "measured": measured}


async def evaluate_no_card_overlap(page: Any, selector: str, thresholds: dict[str, Any]) -> dict[str, Any]:
    measured = await page.evaluate(
        """
        (sel) => {
          let root = null;
          try { root = document.querySelector(sel); } catch (err) { root = null; }
          if (!root) {
            return { exists: false };
          }
          const nodes = Array.from(root.children)
            .filter((el) => {
              const r = el.getBoundingClientRect();
              return r.width > 1 && r.height > 1;
            })
            .slice(0, 16);
          let maxRatio = 0;
          for (let i = 0; i < nodes.length; i += 1) {
            const a = nodes[i].getBoundingClientRect();
            const aArea = Math.max(1, a.width * a.height);
            for (let j = i + 1; j < nodes.length; j += 1) {
              const b = nodes[j].getBoundingClientRect();
              const bArea = Math.max(1, b.width * b.height);
              const x = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
              const y = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
              const overlap = x * y;
              const ratio = overlap / Math.max(1, Math.min(aArea, bArea));
              if (ratio > maxRatio) {
                maxRatio = ratio;
              }
            }
          }
          return {
            exists: true,
            item_count: nodes.length,
            max_overlap_ratio: maxRatio
          };
        }
        """,
        selector,
    )
    if not measured.get("exists"):
        return {"status": "fail", "reason": "selector_not_found", "measured": measured}
    allowed = float(thresholds.get("max_overlap_ratio", 0.0))
    observed = float(measured.get("max_overlap_ratio", 0.0))
    if observed > allowed:
        return {"status": "fail", "reason": "overlap_detected", "measured": measured}
    return {"status": "pass", "reason": "ok", "measured": measured}


async def evaluate_card_size_balance(page: Any, selector: str, thresholds: dict[str, Any]) -> dict[str, Any]:
    measured = await page.evaluate(
        """
        (sel) => {
          let root = null;
          try { root = document.querySelector(sel); } catch (err) { root = null; }
          if (!root) {
            return { exists: false };
          }
          const widths = Array.from(root.children)
            .map((el) => el.getBoundingClientRect().width)
            .filter((v) => v > 1)
            .slice(0, 16);
          if (!widths.length) {
            return { exists: true, item_count: 0 };
          }
          const minWidth = Math.min(...widths);
          const maxWidth = Math.max(...widths);
          return {
            exists: true,
            item_count: widths.length,
            min_width_px: minWidth,
            max_width_px: maxWidth,
            width_ratio: maxWidth / Math.max(1, minWidth)
          };
        }
        """,
        selector,
    )
    if not measured.get("exists"):
        return {"status": "fail", "reason": "selector_not_found", "measured": measured}
    if int(measured.get("item_count", 0)) < 2:
        return {"status": "skipped", "reason": "insufficient_items", "measured": measured}

    max_ratio = float(thresholds.get("max_width_ratio", 1.8))
    ratio = float(measured.get("width_ratio", 1.0))
    if ratio > max_ratio:
        return {"status": "fail", "reason": "card_width_ratio_too_high", "measured": measured}
    max_width = thresholds.get("max_width_px_desktop")
    if max_width is not None and float(measured.get("max_width_px", 0.0)) > float(max_width):
        return {"status": "fail", "reason": "card_width_too_large", "measured": measured}
    return {"status": "pass", "reason": "ok", "measured": measured}


async def evaluate_stack_on_breakpoint(
    page: Any,
    selector: str,
    thresholds: dict[str, Any],
    width: int,
) -> dict[str, Any]:
    stack_at = int(thresholds.get("stack_at_or_below_px", 768))
    if width > stack_at:
        return {"status": "skipped", "reason": "outside_stack_breakpoint", "measured": {"width": width}}

    overlap_result = await evaluate_no_card_overlap(page, selector, {"max_overlap_ratio": 0.0})
    if overlap_result["status"] == "fail":
        return {
            "status": "fail",
            "reason": "overlap_detected_at_stack_breakpoint",
            "measured": overlap_result["measured"],
        }
    return {"status": "pass", "reason": "ok", "measured": overlap_result["measured"]}


async def evaluate_header_consistency(page: Any, thresholds: dict[str, Any]) -> dict[str, Any]:
    measured = await page.evaluate(
        """
        () => {
          const nav = document.querySelector(".site-nav a");
          const header = document.querySelector(".header-inner");
          const icon = document.querySelector(".lv-navbar-icon-link, .btn-theme-toggle");
          if (!header || !nav) {
            return { exists: false };
          }
          const navStyle = getComputedStyle(nav);
          const headerStyle = getComputedStyle(header);
          const iconStyle = icon ? getComputedStyle(icon) : null;
          return {
            exists: true,
            nav_font_px: parseFloat(navStyle.fontSize || "0"),
            nav_weight: parseFloat(navStyle.fontWeight || "0"),
            header_min_height_px: parseFloat(headerStyle.minHeight || "0"),
            icon_width_px: iconStyle ? parseFloat(iconStyle.width || "0") : null,
            icon_height_px: iconStyle ? parseFloat(iconStyle.height || "0") : null
          };
        }
        """
    )
    if not measured.get("exists"):
        return {"status": "fail", "reason": "header_or_nav_missing", "measured": measured}
    min_font = float(thresholds.get("nav_font_px_min", 13.0))
    max_font = float(thresholds.get("nav_font_px_max", 16.0))
    min_height = float(thresholds.get("header_min_height_px", 64.0))
    nav_font = float(measured.get("nav_font_px", 0.0))
    header_h = float(measured.get("header_min_height_px", 0.0))
    if nav_font < min_font or nav_font > max_font:
        return {"status": "fail", "reason": "nav_font_out_of_range", "measured": measured}
    if header_h < min_height:
        return {"status": "fail", "reason": "header_min_height_too_small", "measured": measured}
    return {"status": "pass", "reason": "ok", "measured": measured}


async def evaluate_footer_readability(
    page: Any,
    thresholds: dict[str, Any],
    width: int,
) -> dict[str, Any]:
    max_mobile = int(thresholds.get("max_mobile_width_px", 768))
    if width > max_mobile:
        return {"status": "skipped", "reason": "outside_mobile_width", "measured": {"width": width}}
    measured = await page.evaluate(
        """
        () => {
          const inner = document.querySelector(".footer-inner");
          const link = document.querySelector(".footer-links a");
          const copy = document.querySelector(".lv-footer-copy");
          if (!inner || !link || !copy) {
            return { exists: false };
          }
          const innerStyle = getComputedStyle(inner);
          const linkStyle = getComputedStyle(link);
          const copyStyle = getComputedStyle(copy);
          return {
            exists: true,
            inner_font_px: parseFloat(innerStyle.fontSize || "0"),
            link_font_px: parseFloat(linkStyle.fontSize || "0"),
            link_weight: parseFloat(linkStyle.fontWeight || "0"),
            copy_font_px: parseFloat(copyStyle.fontSize || "0")
          };
        }
        """
    )
    if not measured.get("exists"):
        return {"status": "fail", "reason": "footer_elements_missing", "measured": measured}
    min_link = float(thresholds.get("min_link_font_px", 14.0))
    min_copy = float(thresholds.get("min_copy_font_px", 13.5))
    if float(measured.get("link_font_px", 0.0)) < min_link:
        return {"status": "fail", "reason": "footer_link_font_too_small", "measured": measured}
    if float(measured.get("copy_font_px", 0.0)) < min_copy:
        return {"status": "fail", "reason": "footer_copy_font_too_small", "measured": measured}
    return {"status": "pass", "reason": "ok", "measured": measured}


async def evaluate_search_dark(page: Any, selector: str, thresholds: dict[str, Any]) -> dict[str, Any]:
    await page.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
    measured = await page.evaluate(
        """
        (sel) => {
          const normalize = (value) => (value || "").toLowerCase().replace(/\\s+/g, "");
          let shell = null;
          try { shell = document.querySelector(sel); } catch (err) { shell = null; }
          if (!shell) {
            shell = document.querySelector(".lv-search-shell");
          }
          if (!shell) {
            return { exists: false };
          }
          const input = shell.querySelector("input[type='search'], input");
          if (!input) {
            return { exists: false, shell_exists: true };
          }
          input.focus();
          const shellStyle = getComputedStyle(shell);
          const inputPlaceholder = getComputedStyle(input, "::placeholder");
          return {
            exists: true,
            placeholder_color: inputPlaceholder.color,
            shell_bg: shellStyle.backgroundColor,
            shell_border: shellStyle.borderColor,
            shell_focus_shadow: shellStyle.boxShadow,
            distinct_placeholder_bg: normalize(inputPlaceholder.color) !== normalize(shellStyle.backgroundColor),
            distinct_border_bg: normalize(shellStyle.borderColor) !== normalize(shellStyle.backgroundColor),
            has_focus_ring: normalize(shellStyle.boxShadow) !== "none"
          };
        }
        """,
        selector,
    )
    if not measured.get("exists"):
        return {"status": "fail", "reason": "search_shell_or_input_missing", "measured": measured}
    need_placeholder_distinct = bool(thresholds.get("require_placeholder_bg_distinction", True))
    need_focus = bool(thresholds.get("require_focus_ring", True))
    if need_placeholder_distinct and not measured.get("distinct_placeholder_bg"):
        return {"status": "fail", "reason": "placeholder_not_distinct", "measured": measured}
    if not measured.get("distinct_border_bg"):
        return {"status": "fail", "reason": "search_border_not_distinct", "measured": measured}
    if need_focus and not measured.get("has_focus_ring"):
        return {"status": "fail", "reason": "focus_ring_missing", "measured": measured}
    return {"status": "pass", "reason": "ok", "measured": measured}


async def evaluate_intent(page: Any, intent: dict[str, Any], width: int) -> dict[str, Any]:
    intent_type = str(intent.get("intent_type", "")).strip()
    selector = str(intent.get("locator_css", "")).strip() or "body"
    thresholds = as_json_dict(intent.get("thresholds", {}))

    if intent_type == "carousel_horizontal":
        return await evaluate_carousel_horizontal(page, selector, thresholds)
    if intent_type == "cta_uniqueness_within_section":
        return await evaluate_cta_uniqueness(page, selector, thresholds)
    if intent_type == "no_card_overlap":
        return await evaluate_no_card_overlap(page, selector, thresholds)
    if intent_type == "card_size_balance":
        return await evaluate_card_size_balance(page, selector, thresholds)
    if intent_type == "stack_on_breakpoint":
        return await evaluate_stack_on_breakpoint(page, selector, thresholds, width)
    if intent_type == "header_token_consistency":
        return await evaluate_header_consistency(page, thresholds)
    if intent_type == "footer_readability_mobile":
        return await evaluate_footer_readability(page, thresholds, width)
    if intent_type == "search_chrome_contrast_dark":
        return await evaluate_search_dark(page, selector, thresholds)
    if intent_type == "section_spacing_rhythm":
        return {"status": "skipped", "reason": "stub_not_implemented", "measured": {}}

    return {"status": "skipped", "reason": "unsupported_intent_type", "measured": {}}


def context_kwargs_for_width(width: int, storage_state: str) -> dict[str, Any]:
    is_mobile = width <= 768
    kwargs: dict[str, Any] = {
        "viewport": {"width": width, "height": 844 if is_mobile else 900},
        "device_scale_factor": 2 if is_mobile else 1,
        "is_mobile": is_mobile,
        "has_touch": is_mobile,
    }
    if is_mobile:
        kwargs["user_agent"] = MOBILE_USER_AGENT
    if storage_state:
        kwargs["storage_state"] = storage_state
    return kwargs


def severity_order(severity: str) -> int:
    mapping = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    return mapping.get(severity, 99)


async def run(args: argparse.Namespace) -> int:
    if async_playwright is None:
        print("Missing dependency: playwright")
        print("Install with:")
        print(
            "  python -m pip install -r "
            "skills/webpage-visual-perfection-audit/requirements.txt"
        )
        print("  python -m playwright install chromium")
        if playwright_import_error:
            print(f"Import error: {playwright_import_error}")
        return 2
    playwright_factory = async_playwright

    base_url = normalize_base_url(args.base_url)
    pages_json_path = Path(args.pages_json).resolve()
    intent_catalog_path = Path(args.intent_catalog).resolve()
    output_dir = Path(args.output_dir).resolve()
    screenshots_dir = output_dir / "conformance_screenshots"
    output_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    if not pages_json_path.exists():
        print(f"[error] --pages-json not found: {pages_json_path}")
        return 1
    if not intent_catalog_path.exists():
        print(f"[error] --intent-catalog not found: {intent_catalog_path}")
        return 1
    if args.storage_state:
        state_file = Path(args.storage_state).resolve()
        if not state_file.exists():
            print(f"[error] --storage-state not found: {state_file}")
            return 1
        storage_state = str(state_file)
    else:
        storage_state = ""

    raw_pages_payload = json.loads(pages_json_path.read_text(encoding="utf-8"))
    raw_catalog_payload = json.loads(intent_catalog_path.read_text(encoding="utf-8"))

    pages_payload = as_json_dict(raw_pages_payload)
    catalog_payload = as_json_dict(raw_catalog_payload)

    pages = as_json_dict_list(pages_payload.get("pages", []))
    intents = as_json_dict_list(catalog_payload.get("intents", []))
    if not pages or not intents:
        print("[error] pages or intents are empty.")
        return 1

    route_to_url: dict[str, str] = {}
    for page in pages:
        url = str(page.get("url", "")).strip()
        if not url:
            continue
        route_to_url[normalize_route(url)] = url

    plan: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for intent in intents:
        route_url = route_url_for_intent(intent, route_to_url, base_url)
        breakpoints: list[int] = [int(v) for v in intent.get("breakpoints", []) if int(v) > 0]
        if not breakpoints:
            breakpoints = [1440, 390]
        if args.max_breakpoints_per_intent and args.max_breakpoints_per_intent > 0:
            breakpoints = breakpoints[: args.max_breakpoints_per_intent]
        for width in breakpoints:
            key = (route_url, width)
            plan.setdefault(key, []).append(intent)

    results: list[dict[str, Any]] = []

    async with playwright_factory() as p:
        browser = await p.chromium.launch(headless=not args.headed)

        for (route_url, width), intents_for_page in sorted(plan.items(), key=lambda item: (item[0][0], item[0][1])):
            context = await browser.new_context(**context_kwargs_for_width(width, storage_state))
            page = await context.new_page()
            page.set_default_timeout(args.timeout_ms)

            navigation_error = ""
            try:
                await page.goto(route_url, wait_until="domcontentloaded", timeout=args.timeout_ms)
                await page.wait_for_load_state("networkidle", timeout=args.timeout_ms)
                await page.wait_for_timeout(args.wait_ms)
            except PlaywrightError as exc:
                navigation_error = str(exc)[:500]

            for intent in intents_for_page:
                intent_id = str(intent.get("intent_id", "INT-UNKNOWN"))
                outcome: dict[str, Any]
                if navigation_error:
                    outcome = {"status": "error", "reason": "navigation_failed", "measured": {"error": navigation_error}}
                else:
                    try:
                        outcome = await evaluate_intent(page, intent, width)
                    except PlaywrightError as exc:
                        outcome = {"status": "error", "reason": "evaluation_error", "measured": {"error": str(exc)[:500]}}

                screenshot_rel: str | None = None
                if outcome["status"] == "fail":
                    shot_name = f"{slugify(intent_id)}-w{width}.png"
                    shot_path = screenshots_dir / shot_name
                    try:
                        await page.screenshot(path=str(shot_path), full_page=True, animations="disabled")
                        screenshot_rel = to_rel(shot_path, output_dir)
                    except PlaywrightError:
                        screenshot_rel = None

                results.append(
                    {
                        "intent_id": intent_id,
                        "route": intent.get("route"),
                        "route_url": route_url,
                        "intent_type": intent.get("intent_type"),
                        "confidence": float(intent.get("confidence", 0.0)),
                        "severity_if_broken": intent.get("severity_if_broken", "Low"),
                        "width_px": width,
                        "status": outcome["status"],
                        "reason": outcome.get("reason", ""),
                        "measured": outcome.get("measured", {}),
                        "thresholds": intent.get("thresholds", {}),
                        "screenshot_path": screenshot_rel,
                    }
                )

            await context.close()

        await browser.close()

    status_counts: dict[str, int] = {}
    for row in results:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1

    rollup: dict[str, dict[str, Any]] = {}
    for row in results:
        key = row["intent_id"]
        current = rollup.get(key)
        if current is None:
            rollup[key] = {
                "intent_id": key,
                "route": row["route"],
                "intent_type": row["intent_type"],
                "severity_if_broken": row["severity_if_broken"],
                "confidence": row["confidence"],
                "statuses": [row["status"]],
            }
        else:
            current["statuses"].append(row["status"])

    for value in rollup.values():
        statuses = value["statuses"]
        if "fail" in statuses:
            value["overall_status"] = "fail"
        elif "error" in statuses:
            value["overall_status"] = "error"
        elif "pass" in statuses:
            value["overall_status"] = "pass"
        else:
            value["overall_status"] = "skipped"

    conformance_payload: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "pages_json": str(pages_json_path),
        "intent_catalog": str(intent_catalog_path),
        "strict_high_confidence": bool(args.strict_high_confidence),
        "result_count": len(results),
        "summary": status_counts,
        "rollup": sorted(rollup.values(), key=lambda row: (row["route"] or "", row["intent_id"])),
        "results": results,
    }

    conformance_json = output_dir / "intent_conformance.json"
    violations_md = output_dir / "intent_violations.md"
    conformance_json.write_text(json.dumps(conformance_payload, indent=2), encoding="utf-8")

    failed_rows = [row for row in results if row["status"] == "fail"]
    failed_rows.sort(
        key=lambda row: (
            severity_order(str(row.get("severity_if_broken", "Low"))),
            str(row.get("route") or ""),
            str(row.get("intent_id") or ""),
            int(row.get("width_px") or 0),
        )
    )

    lines: list[str] = []
    lines.append("# Intent Violations (Stage 4 Stub)")
    lines.append("")
    lines.append(f"- Generated at UTC: `{conformance_payload['generated_at_utc']}`")
    lines.append(f"- Result count: `{len(results)}`")
    lines.append(f"- Failed checks: `{len(failed_rows)}`")
    lines.append("")
    if not failed_rows:
        lines.append("No failed intent checks were recorded in this run.")
    else:
        for idx, row in enumerate(failed_rows, start=1):
            lines.append(
                f"{idx}. `{row['intent_id']}` | {row['severity_if_broken']} | "
                f"`{row['route_url']}` | width `{row['width_px']}`"
            )
            lines.append(f"- Intent type: `{row['intent_type']}`")
            lines.append(f"- Reason: `{row['reason']}`")
            lines.append(f"- Screenshot: `{row['screenshot_path'] or 'MISSING'}`")
            lines.append(f"- Measured: `{json.dumps(row['measured'], sort_keys=True)}`")
            lines.append("")
    violations_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[done] Conformance JSON: {conformance_json}")
    print(f"[done] Violations markdown: {violations_md}")
    print(f"[done] Failure screenshots dir: {screenshots_dir}")

    blocking = [
        row
        for row in results
        if row["status"] == "fail"
        and float(row.get("confidence", 0.0)) >= 0.9
        and str(row.get("severity_if_broken", "")).lower() in {"high", "critical"}
    ]

    if args.strict_high_confidence and blocking:
        print(
            "[error] Strict high-confidence gate failed: "
            f"{len(blocking)} blocking failures."
        )
        return 1
    return 0


def main() -> int:
    args = parse_args()
    try:
        if args.timeout_ms < 1000:
            raise ValueError("--timeout-ms must be >= 1000")
        if args.wait_ms < 0:
            raise ValueError("--wait-ms must be >= 0")
        if args.max_breakpoints_per_intent < 0:
            raise ValueError("--max-breakpoints-per-intent must be >= 0")
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        print("Interrupted.")
        return 130
    except Exception as exc:
        print(f"[error] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
