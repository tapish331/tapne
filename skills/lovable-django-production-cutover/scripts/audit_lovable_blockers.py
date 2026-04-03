#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final


@dataclass(frozen=True)
class PatternSpec:
    regex: re.Pattern[str]
    recommendations: tuple[str, ...]


PATTERNS: Final[dict[str, PatternSpec]] = {
    "mock_data_import": PatternSpec(
        regex=re.compile(r"\bmockData\b"),
        recommendations=(
            "Replace `lovable/src/data/mockData.ts` through an external source-override build.",
            "Also inspect fake-action components that still depend on mock exports.",
        ),
    ),
    "inline_mock_literal": PatternSpec(
        regex=re.compile(r"\b(?:const|let|var)\s+mock[A-Za-z0-9_]*\s*="),
        recommendations=(
            "Inspect inline mock arrays/objects that bypass `mockData` and replace them through external overrides or live API/bootstrap data.",
        ),
    ),
    "local_storage": PatternSpec(
        regex=re.compile(r"\blocalStorage\b"),
        recommendations=(
            "Replace local-only persistence with a Django-backed provider outside `lovable/`.",
        ),
    ),
    "session_storage": PatternSpec(
        regex=re.compile(r"\bsessionStorage\b"),
        recommendations=(
            "Inspect session-scoped storage usage and confirm it is not acting as the system of record.",
        ),
    ),
    "fake_latency": PatternSpec(
        regex=re.compile(r"new\s+Promise\s*\("),
        recommendations=(
            "Inspect the corresponding fake mutation flow and replace it through external overrides or real API calls.",
        ),
    ),
    "fake_seed_user": PatternSpec(
        regex=re.compile(r"users\s*\[\s*0\s*\]"),
        recommendations=(
            "Replace seeded-user auth behavior with Django session-backed identity.",
        ),
    ),
    "browser_router": PatternSpec(
        regex=re.compile(r"\bBrowserRouter\b"),
        recommendations=(
            "Decide whether route ownership can stay in Django shell/fallback or needs an external override for `lovable/src/App.tsx`.",
        ),
    ),
}

SOURCE_SUFFIXES: Final[set[str]] = {".ts", ".tsx", ".js", ".jsx", ".css"}
MAX_PRINTED_MATCHES_PER_PATTERN: Final[int] = 40


def _trimmed_snippet(line: str, *, max_length: int = 160) -> str:
    snippet = " ".join(line.strip().split())
    if len(snippet) <= max_length:
        return snippet
    return f"{snippet[: max_length - 3]}..."


def collect_matches(src_root: Path) -> dict[str, list[str]]:
    results: dict[str, list[str]] = {key: [] for key in PATTERNS}
    for path in sorted(src_root.rglob("*")):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="ignore")

        rel_path = str(path.relative_to(src_root.parent)).replace("\\", "/")
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            for key, spec in PATTERNS.items():
                if not spec.regex.search(raw_line):
                    continue
                snippet = _trimmed_snippet(raw_line)
                results[key].append(f"{rel_path}:{line_number}: {snippet}")
    return results


def print_report(results: dict[str, list[str]]) -> None:
    print("Lovable production blocker audit")
    print("")
    for key, matches in results.items():
        print(f"{key}: {len(matches)}")
        for match in matches[:MAX_PRINTED_MATCHES_PER_PATTERN]:
            print(f"  - {match}")
        if len(matches) > MAX_PRINTED_MATCHES_PER_PATTERN:
            remaining = len(matches) - MAX_PRINTED_MATCHES_PER_PATTERN
            print(f"  - ... {remaining} more")
        for recommendation in PATTERNS[key].recommendations:
            print(f"  -> {recommendation}")
        print("")


def audit_override_app(repo_root: Path) -> list[str]:
    """
    Check frontend_spa/src/App.tsx for the two regressions that caused the
    wrong-font / no-carousel / no-tabs production incident:

    1. Any @frontend/pages/* import other than UnderConstructionPage means a
       custom stripped-down page is being used instead of the real Lovable page.
    2. Missing providers (QueryClientProvider, DraftProvider) cause silent
       runtime failures across all pages.
    """
    issues: list[str] = []
    app_path = repo_root / "frontend_spa" / "src" / "App.tsx"
    if not app_path.is_file():
        issues.append(
            f"frontend_spa/src/App.tsx not found at {app_path}. "
            "The override App.tsx is required."
        )
        return issues

    text = app_path.read_text(encoding="utf-8")

    # Check for forbidden @frontend/pages/* imports (anything except UnderConstructionPage)
    for line_no, line in enumerate(text.splitlines(), 1):
        if "@frontend/pages/" in line and "UnderConstructionPage" not in line:
            issues.append(
                f"frontend_spa/src/App.tsx:{line_no}: imports from @frontend/pages/* "
                f"other than UnderConstructionPage — this uses a custom stripped-down "
                f"replacement instead of the real Lovable page. "
                f"Change to @/pages/<PageName>.\n  -> {line.strip()}"
            )

    # Check for required providers
    for provider in ("QueryClientProvider", "DraftProvider", "TooltipProvider"):
        if provider not in text:
            issues.append(
                f"frontend_spa/src/App.tsx: missing {provider}. "
                f"The provider tree must match lovable/src/App.tsx exactly. "
                f"Missing providers cause silent runtime failures on all pages."
            )

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit the repo's Lovable frontend for mock/local-only production blockers."
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root containing the lovable/ directory.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    src_root = repo_root / "lovable" / "src"
    if not src_root.is_dir():
        raise SystemExit(f"Lovable source directory not found: {src_root}")

    results = collect_matches(src_root)
    print_report(results)

    # Additional check: override App.tsx integrity
    override_issues = audit_override_app(repo_root)
    if override_issues:
        print("override_app_integrity:")
        for issue in override_issues:
            print(f"  [FAIL] {issue}")
        print("  -> Read references/override-targets.md for the required App.tsx template.")
        print()
    else:
        print("override_app_integrity: OK")
        print("  -> frontend_spa/src/App.tsx uses @/pages/* for all pages; providers present.")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
