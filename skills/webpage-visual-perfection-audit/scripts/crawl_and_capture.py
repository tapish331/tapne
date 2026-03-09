#!/usr/bin/env python3
"""Discover internal webpages and capture real rendered screenshots.

This script is intentionally deterministic and report-focused:
1. Discover user-facing URLs through sitemap seeds and browser crawling.
2. Capture full-page screenshots in desktop and mobile viewports.
3. Write structured artifacts for a page-by-page visual QA workflow.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

PLAYWRIGHT_IMPORT_ERROR: Exception | None = None
try:
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import async_playwright
except ImportError as exc:  # pragma: no cover - environment dependent
    PlaywrightError = Exception  # type: ignore[assignment]
    async_playwright = None  # type: ignore[assignment]
    PLAYWRIGHT_IMPORT_ERROR = exc


DESKTOP_VIEWPORT = {
    "name": "desktop",
    "viewport": {"width": 1440, "height": 900},
    "device_scale_factor": 1,
    "is_mobile": False,
    "has_touch": False,
}

MOBILE_VIEWPORT = {
    "name": "mobile",
    "viewport": {"width": 390, "height": 844},
    "device_scale_factor": 2,
    "is_mobile": True,
    "has_touch": True,
    "user_agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 "
        "Safari/604.1"
    ),
}

COOKIE_SELECTORS = [
    "button:has-text('Accept all')",
    "button:has-text('Accept All')",
    "button:has-text('I agree')",
    "button:has-text('Agree')",
    "button:has-text('Accept')",
    "button:has-text('Allow all')",
    "[aria-label='Accept all']",
    "[id*='accept'][role='button']",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover internal URLs and capture full-page screenshots."
    )
    parser.add_argument("--base-url", required=True, help="Primary website URL.")
    parser.add_argument(
        "--output-dir",
        default="artifacts/visual-audit",
        help="Output directory for screenshots and reports.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=200,
        help="Maximum number of pages to crawl and capture.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=4,
        help="Maximum link depth from seeds.",
    )
    parser.add_argument(
        "--sitemap-url",
        action="append",
        default=[],
        help="Sitemap XML URL (repeatable).",
    )
    parser.add_argument(
        "--seed-url",
        action="append",
        default=[],
        help="Additional starting URL (repeatable).",
    )
    parser.add_argument(
        "--include-regex",
        action="append",
        default=[],
        help="Only include URLs matching at least one regex (repeatable).",
    )
    parser.add_argument(
        "--exclude-regex",
        action="append",
        default=[],
        help="Exclude URLs matching any regex (repeatable).",
    )
    parser.add_argument(
        "--storage-state",
        default="",
        help="Path to Playwright storage_state JSON for authenticated routes.",
    )
    parser.add_argument(
        "--allow-subdomains",
        action="store_true",
        help="Treat subdomains as internal.",
    )
    parser.add_argument(
        "--no-desktop",
        action="store_true",
        help="Skip desktop screenshots.",
    )
    parser.add_argument(
        "--no-mobile",
        action="store_true",
        help="Skip mobile screenshots.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=45000,
        help="Playwright navigation timeout.",
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=1200,
        help="Extra wait after page load for late paints.",
    )
    return parser.parse_args()


def canonicalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        return ""
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return ""

    netloc = hostname
    if parsed.port:
        netloc = f"{hostname}:{parsed.port}"

    path = re.sub(r"/+", "/", parsed.path or "/")
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)), doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def url_to_slug(url: str, max_len: int = 80) -> str:
    parsed = urlsplit(url)
    base = parsed.netloc + (parsed.path or "/")
    if parsed.query:
        base += "-" + parsed.query
    base = re.sub(r"[^A-Za-z0-9]+", "-", base).strip("-").lower() or "root"
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"{base[:max_len]}-{digest}"


def is_internal_url(url: str, base_host: str, allow_subdomains: bool) -> bool:
    hostname = (urlsplit(url).hostname or "").lower()
    if not hostname:
        return False
    if hostname == base_host:
        return True
    return allow_subdomains and hostname.endswith(f".{base_host}")


def compile_patterns(patterns: list[str], label: str) -> list[re.Pattern[str]]:
    compiled: list[re.Pattern[str]] = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern))
        except re.error as exc:
            raise ValueError(f"Invalid {label} regex `{pattern}`: {exc}") from exc
    return compiled


def url_passes_filters(
    url: str,
    include_regexes: list[re.Pattern[str]],
    exclude_regexes: list[re.Pattern[str]],
) -> bool:
    if include_regexes and not any(regex.search(url) for regex in include_regexes):
        return False
    if any(regex.search(url) for regex in exclude_regexes):
        return False
    return True


def fetch_text(url: str, timeout_seconds: int = 20) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            )
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read().decode("utf-8", errors="replace")


def xml_tag_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def discover_from_sitemaps(
    sitemap_urls: list[str],
    include_regexes: list[re.Pattern[str]],
    exclude_regexes: list[re.Pattern[str]],
    base_host: str,
    allow_subdomains: bool,
) -> set[str]:
    discovered: set[str] = set()
    visited: set[str] = set()
    pending = deque(canonicalize_url(url) for url in sitemap_urls if canonicalize_url(url))

    while pending:
        sitemap_url = pending.popleft()
        if sitemap_url in visited:
            continue
        visited.add(sitemap_url)

        try:
            xml_text = fetch_text(sitemap_url)
            root = ET.fromstring(xml_text)
        except Exception as exc:
            print(f"[warn] Failed to read sitemap {sitemap_url}: {exc}")
            continue

        root_name = xml_tag_name(root.tag)
        if root_name == "sitemapindex":
            for child in root:
                if xml_tag_name(child.tag) != "sitemap":
                    continue
                loc = child.findtext(".//{*}loc") or ""
                loc = canonicalize_url(loc)
                if loc and loc not in visited:
                    pending.append(loc)
            continue

        if root_name != "urlset":
            print(f"[warn] Unsupported sitemap root in {sitemap_url}: {root_name}")
            continue

        for child in root:
            if xml_tag_name(child.tag) != "url":
                continue
            loc = child.findtext(".//{*}loc") or ""
            loc = canonicalize_url(loc)
            if not loc:
                continue
            if not is_internal_url(loc, base_host, allow_subdomains):
                continue
            if not url_passes_filters(loc, include_regexes, exclude_regexes):
                continue
            discovered.add(loc)

    return discovered


async def dismiss_common_banners(page: Any) -> None:
    for selector in COOKIE_SELECTORS:
        try:
            locator = page.locator(selector).first
            if await locator.is_visible():
                await locator.click(timeout=800)
                await page.wait_for_timeout(250)
                return
        except PlaywrightError:
            continue
    try:
        await page.keyboard.press("Escape")
    except PlaywrightError:
        pass


async def auto_scroll(page: Any, step_wait_ms: int, max_steps: int = 25) -> None:
    last_height = -1
    stable_steps = 0
    for _ in range(max_steps):
        try:
            height = await page.evaluate(
                "() => document.body ? document.body.scrollHeight : 0"
            )
        except PlaywrightError:
            break
        await page.evaluate(
            "() => window.scrollTo(0, document.body ? document.body.scrollHeight : 0)"
        )
        await page.wait_for_timeout(step_wait_ms)
        if height == last_height:
            stable_steps += 1
            if stable_steps >= 2:
                break
        else:
            stable_steps = 0
        last_height = height
    await page.evaluate("() => window.scrollTo(0, 0)")
    await page.wait_for_timeout(150)


def to_rel(path: Path, base: Path) -> str:
    return path.resolve().relative_to(base.resolve()).as_posix()


async def crawl_urls(
    browser: Any,
    base_url: str,
    initial_urls: list[str],
    include_regexes: list[re.Pattern[str]],
    exclude_regexes: list[re.Pattern[str]],
    base_host: str,
    allow_subdomains: bool,
    max_pages: int,
    max_depth: int,
    timeout_ms: int,
    wait_ms: int,
    storage_state: str,
) -> list[dict[str, Any]]:
    context_kwargs: dict[str, Any] = {
        "viewport": {"width": 1366, "height": 900},
    }
    if storage_state:
        context_kwargs["storage_state"] = storage_state

    context = await browser.new_context(**context_kwargs)
    page = await context.new_page()

    queue: deque[tuple[str, int, str]] = deque()
    queued: set[str] = set()
    for url in initial_urls:
        if url in queued:
            continue
        queue.append((url, 0, "seed"))
        queued.add(url)

    visited: set[str] = set()
    discovered_records: list[dict[str, Any]] = []

    while queue and len(discovered_records) < max_pages:
        url, depth, source = queue.popleft()
        queued.discard(url)
        if url in visited:
            continue
        visited.add(url)

        print(f"[crawl] {len(discovered_records) + 1}/{max_pages} depth={depth} {url}")
        record: dict[str, Any] = {
            "url": url,
            "depth": depth,
            "source": source,
            "title": "",
            "http_status": None,
            "crawl_status": "ok",
            "crawl_error": "",
            "links_found": 0,
            "screenshots": {},
            "capture_status": {},
            "capture_errors": [],
        }

        links: list[str] = []
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.wait_for_load_state("networkidle", timeout=timeout_ms)
            await page.wait_for_timeout(wait_ms)
            record["http_status"] = response.status if response else None
            record["title"] = await page.title()
            raw_links: list[str] = await page.eval_on_selector_all(
                "a[href]",
                "elements => elements.map(element => element.getAttribute('href') || '')",
            )
            for href in raw_links:
                absolute = canonicalize_url(urljoin(url, href))
                if not absolute:
                    continue
                if not is_internal_url(absolute, base_host, allow_subdomains):
                    continue
                if not url_passes_filters(absolute, include_regexes, exclude_regexes):
                    continue
                links.append(absolute)
        except PlaywrightError as exc:
            record["crawl_status"] = "error"
            record["crawl_error"] = str(exc)[:500]

        links = sorted(set(links))
        record["links_found"] = len(links)
        discovered_records.append(record)

        if record["crawl_status"] != "ok" or depth >= max_depth:
            continue

        for link in links:
            if link in visited or link in queued:
                continue
            if len(discovered_records) + len(queue) >= max_pages:
                break
            queue.append((link, depth + 1, url))
            queued.add(link)

    await context.close()
    return discovered_records


async def capture_screenshots(
    browser: Any,
    pages: list[dict[str, Any]],
    output_dir: Path,
    viewport_configs: list[dict[str, Any]],
    timeout_ms: int,
    wait_ms: int,
    storage_state: str,
) -> None:
    screenshots_root = output_dir / "screenshots"
    screenshots_root.mkdir(parents=True, exist_ok=True)

    for viewport_config in viewport_configs:
        viewport_name = viewport_config["name"]
        target_dir = screenshots_root / viewport_name
        target_dir.mkdir(parents=True, exist_ok=True)

        context_kwargs: dict[str, Any] = {
            "viewport": viewport_config["viewport"],
            "device_scale_factor": viewport_config["device_scale_factor"],
            "is_mobile": viewport_config["is_mobile"],
            "has_touch": viewport_config["has_touch"],
        }
        if viewport_config.get("user_agent"):
            context_kwargs["user_agent"] = viewport_config["user_agent"]
        if storage_state:
            context_kwargs["storage_state"] = storage_state

        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()

        for idx, record in enumerate(pages, start=1):
            url = record["url"]
            file_name = f"{idx:03d}-{url_to_slug(url)}.png"
            screenshot_path = target_dir / file_name
            print(f"[shot:{viewport_name}] {idx}/{len(pages)} {url}")
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                await page.wait_for_load_state("networkidle", timeout=timeout_ms)
                await dismiss_common_banners(page)
                await auto_scroll(page, step_wait_ms=max(250, wait_ms // 2))
                await page.wait_for_timeout(wait_ms)
                await page.screenshot(
                    path=str(screenshot_path),
                    full_page=True,
                    animations="disabled",
                )
                record["screenshots"][viewport_name] = to_rel(screenshot_path, output_dir)
                record["capture_status"][viewport_name] = "ok"
                if record["http_status"] is None and response:
                    record["http_status"] = response.status
            except PlaywrightError as exc:
                record["screenshots"][viewport_name] = None
                record["capture_status"][viewport_name] = "error"
                record["capture_errors"].append(f"{viewport_name}: {str(exc)[:500]}")

        await context.close()


def write_pages_json(output_dir: Path, run_data: dict[str, Any]) -> Path:
    output_path = output_dir / "pages.json"
    output_path.write_text(json.dumps(run_data, indent=2), encoding="utf-8")
    return output_path


def write_report_template(
    output_dir: Path,
    run_data: dict[str, Any],
    enabled_viewports: list[str],
) -> Path:
    pages = run_data["pages"]
    lines: list[str] = []
    lines.append("# Visual QA Report")
    lines.append("")
    lines.append("## Audit Metadata")
    lines.append(f"- Base URL: `{run_data['base_url']}`")
    lines.append(f"- Generated At (UTC): `{run_data['generated_at_utc']}`")
    lines.append(f"- Total Pages: `{len(pages)}`")
    lines.append(f"- Viewports: `{', '.join(enabled_viewports)}`")
    lines.append("")
    lines.append("## Severity Summary")
    lines.append("- Critical: 0")
    lines.append("- High: 0")
    lines.append("- Medium: 0")
    lines.append("- Low: 0")
    lines.append("")
    lines.append(
        "Use references/visual-rubric.md for evaluation and "
        "references/report-schema.md for required issue fields."
    )
    lines.append("")

    for idx, page in enumerate(pages, start=1):
        lines.append(f"## Page {idx}: `{page['url']}`")
        lines.append(f"- Title: `{page.get('title') or ''}`")
        lines.append(f"- Crawl depth: `{page.get('depth')}`")
        lines.append(f"- Crawl status: `{page.get('crawl_status')}`")
        lines.append(f"- HTTP status: `{page.get('http_status')}`")
        for viewport_name in enabled_viewports:
            image_path = page.get("screenshots", {}).get(viewport_name) or "MISSING"
            lines.append(f"- {viewport_name.title()} screenshot: `{image_path}`")
        lines.append("")
        lines.append("### Findings")
        lines.append("- Status: FAIL")
        lines.append("- Defect count: 0")
        lines.append("")
        lines.append("### Defects")
        lines.append("1. ISSUE-ID")
        lines.append("- Severity: Critical|High|Medium|Low")
        lines.append("- Category: Layout|Spacing|Typography|Color|Component|Media|Responsive|Motion|Polish")
        lines.append("- Viewport: desktop|mobile|both")
        lines.append("- Evidence: screenshot path and precise area")
        lines.append("- Why imperfect: concise rationale")
        lines.append("- Suggested fix: concrete implementation guidance")
        lines.append("- Acceptance criteria: objective pass condition")
        lines.append("")

    report_path = output_dir / "report_template.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def validate_args(args: argparse.Namespace) -> None:
    if args.max_pages <= 0:
        raise ValueError("--max-pages must be > 0")
    if args.max_depth < 0:
        raise ValueError("--max-depth must be >= 0")
    if args.timeout_ms < 1000:
        raise ValueError("--timeout-ms must be >= 1000")
    if args.wait_ms < 0:
        raise ValueError("--wait-ms must be >= 0")
    if args.no_desktop and args.no_mobile:
        raise ValueError("At least one viewport must be enabled.")

    base_url = canonicalize_url(args.base_url)
    if not base_url:
        raise ValueError("--base-url must be a valid http/https URL")
    args.base_url = base_url

    if args.storage_state:
        state_file = Path(args.storage_state)
        if not state_file.exists():
            raise ValueError(f"--storage-state file not found: {state_file}")
        args.storage_state = str(state_file.resolve())


async def run(args: argparse.Namespace) -> int:
    if async_playwright is None:
        print("Missing dependency: playwright")
        print("Install with:")
        print(
            "  python -m pip install -r "
            "skills/webpage-visual-perfection-audit/requirements.txt"
        )
        print("  python -m playwright install chromium")
        if PLAYWRIGHT_IMPORT_ERROR:
            print(f"Import error: {PLAYWRIGHT_IMPORT_ERROR}")
        return 2

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    include_regexes = compile_patterns(args.include_regex, "include")
    exclude_regexes = compile_patterns(args.exclude_regex, "exclude")
    base_host = (urlsplit(args.base_url).hostname or "").lower()

    sitemap_urls = list(args.sitemap_url)
    if not sitemap_urls:
        default_sitemap = canonicalize_url(urljoin(args.base_url, "/sitemap.xml"))
        if default_sitemap:
            sitemap_urls.append(default_sitemap)

    seed_urls: set[str] = {args.base_url}
    for raw in args.seed_url:
        canonical = canonicalize_url(raw)
        if canonical:
            seed_urls.add(canonical)

    sitemap_discovered = discover_from_sitemaps(
        sitemap_urls=sitemap_urls,
        include_regexes=include_regexes,
        exclude_regexes=exclude_regexes,
        base_host=base_host,
        allow_subdomains=args.allow_subdomains,
    )
    seed_urls.update(sitemap_discovered)
    initial_urls = sorted(
        url
        for url in seed_urls
        if is_internal_url(url, base_host, args.allow_subdomains)
        and url_passes_filters(url, include_regexes, exclude_regexes)
    )

    if not initial_urls:
        initial_urls = [args.base_url]

    selected_viewports: list[dict[str, Any]] = []
    if not args.no_desktop:
        selected_viewports.append(DESKTOP_VIEWPORT)
    if not args.no_mobile:
        selected_viewports.append(MOBILE_VIEWPORT)

    print(f"[info] Base URL: {args.base_url}")
    print(f"[info] Seeds before crawl: {len(initial_urls)}")
    print(f"[info] Output dir: {output_dir}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        pages = await crawl_urls(
            browser=browser,
            base_url=args.base_url,
            initial_urls=initial_urls,
            include_regexes=include_regexes,
            exclude_regexes=exclude_regexes,
            base_host=base_host,
            allow_subdomains=args.allow_subdomains,
            max_pages=args.max_pages,
            max_depth=args.max_depth,
            timeout_ms=args.timeout_ms,
            wait_ms=args.wait_ms,
            storage_state=args.storage_state,
        )

        if not pages:
            pages = [
                {
                    "url": args.base_url,
                    "depth": 0,
                    "source": "fallback",
                    "title": "",
                    "http_status": None,
                    "crawl_status": "error",
                    "crawl_error": "No crawlable pages discovered.",
                    "links_found": 0,
                    "screenshots": {},
                    "capture_status": {},
                    "capture_errors": [],
                }
            ]

        await capture_screenshots(
            browser=browser,
            pages=pages,
            output_dir=output_dir,
            viewport_configs=selected_viewports,
            timeout_ms=args.timeout_ms,
            wait_ms=args.wait_ms,
            storage_state=args.storage_state,
        )

        await browser.close()

    enabled_viewports = [view["name"] for view in selected_viewports]
    run_data = {
        "base_url": args.base_url,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "page_count": len(pages),
        "enabled_viewports": enabled_viewports,
        "pages": pages,
    }
    pages_json = write_pages_json(output_dir, run_data)
    template_path = write_report_template(output_dir, run_data, enabled_viewports)

    ok_pages = sum(1 for page in pages if page.get("crawl_status") == "ok")
    print(f"[done] Pages listed: {len(pages)} ({ok_pages} crawled successfully)")
    print(f"[done] Metadata: {pages_json}")
    print(f"[done] Report template: {template_path}")
    return 0


def main() -> int:
    args = parse_args()
    try:
        validate_args(args)
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        print("Interrupted.")
        return 130
    except Exception as exc:
        print(f"[error] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
