#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Final


BANNED_BUILD_MARKERS: Final[dict[str, str]] = {
    "mock_data": "mockData",
    "draft_storage_key": "tapne_drafts",
    "local_storage": "localStorage",
    "browser_router": "BrowserRouter",
    "fake_login": "users[0]",
}

REQUIRED_INDEX_MARKERS: Final[dict[str, str]] = {
    "shell_meta": 'name="tapne-frontend-shell"',
    "brand_tokens": "frontend-brand/tokens.css",
    "brand_overrides": "frontend-brand/overrides.css",
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
    for label, banned in BANNED_BUILD_MARKERS.items():
        hits: list[str] = []
        for path in text_files:
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
