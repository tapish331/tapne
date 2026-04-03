#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Final


BANNED_BUILD_MARKERS: Final[dict[str, str]] = {
    "mock_data": "mockData",
    # The specific key used by the old localStorage-only draft context.
    # Generic "localStorage" is intentionally NOT banned here because the
    # Lovable bundle includes a dark-mode theme library that legitimately
    # uses localStorage for color-scheme persistence. Only the app-level
    # draft storage key is a cutover blocker.
    "draft_storage_key": "tapne_drafts",
    "browser_router": "BrowserRouter",
    "fake_login": "users[0]",
}

REQUIRED_INDEX_MARKERS: Final[dict[str, str]] = {
    "shell_meta": 'name="tapne-frontend-shell"',
    "brand_tokens": "frontend-brand/tokens.css",
    "brand_overrides": "frontend-brand/overrides.css",
}

# Markers that must appear somewhere in the JS bundle (not necessarily index.html).
# Component names survive minification as string literals in React dev-tools metadata
# but may be mangled in production. We check the source map (.map files) as a reliable
# signal that the component was included in the build.
REQUIRED_BUNDLE_MARKERS: Final[dict[str, str]] = {
    # The UnderConstruction page is compiled as a React component; its class name may be
    # mangled by minification. The heading string "Under Construction" is a string literal
    # that always survives minification and is a reliable signal the component shipped.
    "under_construction": "Under Construction",
}

FORBIDDEN_INDEX_MARKERS: Final[dict[str, str]] = {
    "external_runtime_dependency": "frontend-runtime.js",
}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def _collect_text_files(build_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(build_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() in {".html", ".js", ".css", ".json", ".svg", ".txt", ".map"}:
            files.append(path)
    return files


def _collect_js_files(build_dir: Path) -> list[Path]:
    """JS-only files — excludes .map files.

    Used for banned markers that must not appear in executed code but may
    legitimately appear in source maps (e.g. TypeScript type-only imports
    from a module that is excluded from the runtime bundle create source-map
    references without contributing any runtime code).
    """
    files: list[Path] = []
    for path in sorted(build_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() in {".html", ".js", ".css", ".json", ".svg", ".txt"}:
            files.append(path)
    return files


def verify_artifact(build_dir: Path) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    notes: list[str] = []

    index_path = build_dir / "index.html"
    if not index_path.is_file():
        failures.append(f"Missing index.html in build directory: {build_dir}")
        return failures, notes

    index_text = _read_text(index_path)
    for key, marker in REQUIRED_INDEX_MARKERS.items():
        if marker not in index_text:
            failures.append(f"Missing required shell marker '{key}' in index.html: {marker}")

    for key, marker in FORBIDDEN_INDEX_MARKERS.items():
        if marker in index_text:
            failures.append(f"Forbidden shell marker '{key}' still present in index.html: {marker}")

    text_files = _collect_text_files(build_dir)
    # JS-only file list: excludes .map files.
    # The mock_data marker is checked against JS files only because source maps
    # legitimately reference mockData.ts for the TypeScript type-only import in
    # CreateTrip.tsx:26 — that import is erased at runtime and does not produce
    # any executed mock code. Checking .map files for this marker produces a
    # false positive that would hide real mock-data regressions in JS bundles.
    js_files = _collect_js_files(build_dir)

    # Check required bundle markers across all text files (JS, maps, etc.)
    for key, marker in REQUIRED_BUNDLE_MARKERS.items():
        found = any(marker in _read_text(f) for f in text_files)
        if not found:
            failures.append(
                f"Required bundle marker '{key}' not found in any build file: {marker}. "
                f"Ensure the UnderConstructionPage component was included in the external override build."
            )
        else:
            notes.append(f"Present: {key} ({marker})")

    # Banned markers that must not appear in JS bundles.
    # mock_data is checked against JS files only (not .map) — see js_files comment above.
    JS_ONLY_BANNED: Final[frozenset[str]] = frozenset({"mock_data"})

    for label, banned in BANNED_BUILD_MARKERS.items():
        search_files = js_files if label in JS_ONLY_BANNED else text_files
        hits: list[str] = []
        for path in search_files:
            text = _read_text(path)
            if banned in text:
                hits.append(str(path.relative_to(build_dir)).replace("\\", "/"))
        if hits:
            failures.append(
                f"Banned marker '{label}' still present ({banned}) in: {', '.join(hits[:8])}"
            )
        else:
            notes.append(f"Clean: {label}")

    notes.append("Artifact check expects runtime config to be injected inline by the serving shell, not loaded from /frontend-runtime.js.")

    # Check that overrides.css in the build is empty or absent (no unsolicited visual overrides).
    for path in text_files:
        if "frontend-brand/overrides" in str(path).replace("\\", "/"):
            content = _read_text(path).strip()
            # Allow a comment-only file (e.g., the header comment), but no real CSS rules.
            non_comment_lines = [
                line for line in content.splitlines()
                if line.strip() and not line.strip().startswith("/*") and not line.strip().startswith("*") and not line.strip().startswith("//")
            ]
            if non_comment_lines:
                failures.append(
                    f"overrides.css contains CSS rules — this file must be empty unless a deliberate visual change was explicitly requested. "
                    f"Found {len(non_comment_lines)} non-comment line(s)."
                )
            else:
                notes.append("Clean: overrides.css is empty (no unsolicited visual overrides).")
            break

    return failures, notes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify that a built Lovable production artifact no longer contains banned mock/local-only markers."
    )
    parser.add_argument("--repo-root", default=".", help="Repository root. Present for workflow symmetry.")
    parser.add_argument("--build-dir", required=True, help="Path to the emitted Lovable production artifact.")
    args = parser.parse_args()

    build_dir = Path(args.build_dir).resolve()
    if not build_dir.is_dir():
        raise SystemExit(f"Build directory not found: {build_dir}")

    failures, notes = verify_artifact(build_dir)

    print("Lovable cutover artifact verification")
    print("")
    print(f"build_dir: {build_dir}")
    print("")

    for note in notes:
        print(f"[OK] {note}")

    if failures:
        print("")
        for failure in failures:
            print(f"[FAIL] {failure}")
        return 1

    print("")
    print("Artifact passed banned-marker verification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
