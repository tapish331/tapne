#!/usr/bin/env python3
"""Capture homepage visual regression snapshots at fixed breakpoints.

This script captures rendered screenshots for `/` at:
1440, 1024, 768, 600, 390.

Optionally, it compares current captures against committed baseline images and
emits a structured summary. It only fails when `--fail-on-diff` is set.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

PLAYWRIGHT_IMPORT_ERROR: Exception | None = None
try:
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import async_playwright
except ImportError as exc:  # pragma: no cover - environment dependent
    PlaywrightError = Exception  # type: ignore[assignment]
    async_playwright = None  # type: ignore[assignment]
    PLAYWRIGHT_IMPORT_ERROR = exc


MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 "
    "Safari/604.1"
)

BREAKPOINTS = [1440, 1024, 768, 600, 390]


@dataclass(frozen=True)
class CaptureResult:
    width: int
    route_url: str
    current_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Capture homepage regression snapshots (/) at 1440, 1024, 768, 600, 390, "
            "with optional baseline comparison."
        )
    )
    parser.add_argument("--base-url", required=True, help="Base URL (http/https).")
    parser.add_argument(
        "--route",
        default="/",
        help="Route to capture (default: /).",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for current snapshots and reports.",
    )
    parser.add_argument(
        "--baseline-dir",
        default="skills/webpage-visual-perfection-audit/snapshots/homepage",
        help="Directory containing baseline snapshots named home-w<width>.png.",
    )
    parser.add_argument(
        "--storage-state",
        default="",
        help="Optional Playwright storage_state JSON for authenticated captures.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=45000,
        help="Navigation timeout in milliseconds.",
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=1200,
        help="Extra wait after network idle for late paints.",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare current snapshots against baseline snapshots.",
    )
    parser.add_argument(
        "--max-diff-ratio",
        type=float,
        default=0.02,
        help=(
            "Maximum changed-pixel ratio allowed when --compare is used and "
            "--fail-on-diff is set."
        ),
    )
    parser.add_argument(
        "--fail-on-diff",
        action="store_true",
        help="Fail with exit code 1 when compared snapshots exceed --max-diff-ratio.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser headed for debugging.",
    )
    return parser.parse_args()


def normalize_base_url(raw: str) -> str:
    value = raw.strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("--base-url must be a valid http/https URL.")
    return value.rstrip("/")


def route_url(base_url: str, route: str) -> str:
    normalized_route = route.strip() or "/"
    if normalized_route.startswith(("http://", "https://")):
        return normalized_route
    if normalized_route.startswith("/"):
        return urljoin(base_url + "/", normalized_route.lstrip("/"))
    return urljoin(base_url + "/", normalized_route)


def context_kwargs(width: int, storage_state: str) -> dict[str, Any]:
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


def changed_pixel_ratio(current_path: Path, baseline_path: Path) -> tuple[float, str]:
    try:
        from PIL import Image, ImageChops
    except ImportError as exc:  # pragma: no cover - dependency/environment specific
        raise RuntimeError(
            "Pillow is required for snapshot comparison. "
            "Install with: python -m pip install Pillow"
        ) from exc

    with Image.open(current_path) as current_image, Image.open(baseline_path) as baseline_image:
        current = current_image.convert("RGBA")
        baseline = baseline_image.convert("RGBA")
        if current.size != baseline.size:
            return 1.0, (
                f"size_mismatch current={current.size[0]}x{current.size[1]} "
                f"baseline={baseline.size[0]}x{baseline.size[1]}"
            )
        diff = ImageChops.difference(current, baseline).convert("L")
        histogram = diff.histogram()
        total = sum(histogram)
        changed = total - histogram[0]
        ratio = changed / max(1, total)
        return ratio, "ok"


def write_summary_markdown(summary_path: Path, payload: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Homepage Snapshot Summary")
    lines.append("")
    lines.append(f"- Generated at UTC: `{payload['generated_at_utc']}`")
    lines.append(f"- Base URL: `{payload['base_url']}`")
    lines.append(f"- Route: `{payload['route']}`")
    lines.append(f"- Compare enabled: `{payload['compare_enabled']}`")
    if payload["compare_enabled"]:
        lines.append(f"- Max diff ratio: `{payload['max_diff_ratio']}`")
        lines.append(f"- Failing widths: `{len(payload['failing_widths'])}`")
    lines.append("")
    lines.append("| Width | Status | Diff Ratio | Current | Baseline |")
    lines.append("|---:|---|---:|---|---|")
    for row in payload["results"]:
        lines.append(
            "| {width} | {status} | {ratio} | `{current}` | `{baseline}` |".format(
                width=row["width"],
                status=row["status"],
                ratio=(
                    f"{row['diff_ratio']:.6f}"
                    if isinstance(row.get("diff_ratio"), float)
                    else "-"
                ),
                current=row["current_path"],
                baseline=row.get("baseline_path", ""),
            )
        )
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def capture_snapshots(args: argparse.Namespace) -> int:
    if async_playwright is None:
        print("Missing dependency: playwright")
        print(
            "Install with: python -m pip install -r "
            "skills/webpage-visual-perfection-audit/requirements.txt"
        )
        print("Then: python -m playwright install chromium")
        if PLAYWRIGHT_IMPORT_ERROR:
            print(f"Import error: {PLAYWRIGHT_IMPORT_ERROR}")
        return 2

    if args.timeout_ms < 1000:
        raise ValueError("--timeout-ms must be >= 1000")
    if args.wait_ms < 0:
        raise ValueError("--wait-ms must be >= 0")
    if args.max_diff_ratio < 0.0 or args.max_diff_ratio > 1.0:
        raise ValueError("--max-diff-ratio must be in [0.0, 1.0].")

    base_url = normalize_base_url(args.base_url)
    resolved_route_url = route_url(base_url, args.route)
    output_dir = Path(args.output_dir).resolve()
    baseline_dir = Path(args.baseline_dir).resolve()
    current_dir = output_dir / "current"
    reports_dir = output_dir / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    current_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    if args.storage_state:
        state_file = Path(args.storage_state).resolve()
        if not state_file.exists():
            print(f"[error] --storage-state not found: {state_file}")
            return 1
        storage_state = str(state_file)
    else:
        storage_state = ""

    captured: list[CaptureResult] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not args.headed)
        for width in BREAKPOINTS:
            context = await browser.new_context(**context_kwargs(width, storage_state))
            page = await context.new_page()
            page.set_default_timeout(args.timeout_ms)
            try:
                await page.goto(resolved_route_url, wait_until="domcontentloaded", timeout=args.timeout_ms)
                await page.wait_for_load_state("networkidle", timeout=args.timeout_ms)
                await page.wait_for_timeout(args.wait_ms)
                current_path = current_dir / f"home-w{width}.png"
                await page.screenshot(path=str(current_path), full_page=True, animations="disabled")
                captured.append(CaptureResult(width=width, route_url=resolved_route_url, current_path=current_path))
                print(f"[captured] width={width} -> {current_path}")
            except PlaywrightError as exc:
                print(f"[error] capture failed at width={width}: {exc}")
                await context.close()
                await browser.close()
                return 1
            await context.close()
        await browser.close()

    results: list[dict[str, Any]] = []
    failing_widths: list[int] = []
    for row in captured:
        payload: dict[str, Any] = {
            "width": row.width,
            "route_url": row.route_url,
            "current_path": str(row.current_path),
            "status": "captured",
        }
        if args.compare:
            baseline_path = baseline_dir / f"home-w{row.width}.png"
            payload["baseline_path"] = str(baseline_path)
            if not baseline_path.exists():
                payload["status"] = "missing_baseline"
                payload["reason"] = "baseline_not_found"
                failing_widths.append(row.width)
            else:
                ratio, reason = changed_pixel_ratio(row.current_path, baseline_path)
                payload["diff_ratio"] = ratio
                payload["reason"] = reason
                if ratio > args.max_diff_ratio:
                    payload["status"] = "diff_exceeds_threshold"
                    failing_widths.append(row.width)
                else:
                    payload["status"] = "match_within_threshold"
        results.append(payload)

    summary_payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "route": args.route,
        "breakpoints": BREAKPOINTS,
        "compare_enabled": bool(args.compare),
        "max_diff_ratio": float(args.max_diff_ratio),
        "failing_widths": failing_widths,
        "results": results,
    }

    summary_json = reports_dir / "homepage_snapshot_summary.json"
    summary_md = reports_dir / "homepage_snapshot_summary.md"
    summary_json.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    write_summary_markdown(summary_md, summary_payload)
    print(f"[done] Snapshot summary JSON: {summary_json}")
    print(f"[done] Snapshot summary MD: {summary_md}")

    if args.fail_on_diff and failing_widths:
        print(
            "[error] Snapshot diff gate failed at widths: "
            + ", ".join(str(v) for v in failing_widths)
        )
        return 1
    return 0


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(capture_snapshots(args))
    except KeyboardInterrupt:
        print("Interrupted.")
        return 130
    except Exception as exc:
        print(f"[error] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
