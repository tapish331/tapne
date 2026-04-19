from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from dotenv import dotenv_values
from pytest import FixtureRequest
from playwright.sync_api import Browser, sync_playwright

from tests.e2e.auth import ensure_storage_state
from tests.e2e.helpers import BrowserAudit, sanitize_name
from tests.e2e.server import DjangoServer, ensure_build_artifact, wait_for_health
from tests.e2e.types import SessionFactory, SessionHandle


def _load_e2e_env_defaults() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.is_file():
        return
    configured = dotenv_values(env_path)
    refresh = configured.get("E2E_REFRESH_STORAGE_STATE")
    if isinstance(refresh, str) and refresh.strip():
        os.environ.setdefault("E2E_REFRESH_STORAGE_STATE", refresh.strip())


_load_e2e_env_defaults()


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def e2e_base_url() -> str:
    return os.getenv("E2E_BASE_URL", "http://127.0.0.1:8123")


@pytest.fixture(scope="session")
def artifacts_root(repo_root: Path) -> Path:
    path = repo_root / "artifacts" / "e2e"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture(scope="session")
def auth_artifacts_root(repo_root: Path) -> Path:
    path = repo_root / "artifacts" / "auth"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture(scope="session", autouse=True)
def verify_build_artifact(repo_root: Path) -> None:
    ensure_build_artifact(repo_root)


@pytest.fixture(scope="session", autouse=True)
def django_server(repo_root: Path, e2e_base_url: str, artifacts_root: Path) -> Iterator[None]:
    if os.getenv("E2E_USE_EXISTING_SERVER", "").lower() in {"1", "true", "yes"}:
        wait_for_health(e2e_base_url)
        yield
        return

    server = DjangoServer(
        repo_root=repo_root,
        base_url=e2e_base_url,
        log_dir=artifacts_root / "server",
    )
    server.start()
    try:
        yield
    finally:
        server.stop()


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    headed = os.getenv("E2E_HEADED", "").lower() in {"1", "true", "yes"}
    slow_mo = int(os.getenv("E2E_SLOW_MO_MS", "0"))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed, slow_mo=slow_mo)
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture
def test_artifact_dir(artifacts_root: Path, request: FixtureRequest) -> Path:
    path = artifacts_root / sanitize_name(request.node.nodeid)
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def session_factory(
    browser: Browser,
    e2e_base_url: str,
    auth_artifacts_root: Path,
    test_artifact_dir: Path,
) -> Iterator[SessionFactory]:
    sessions: list[SessionHandle] = []

    def create(*, name: str, username: str | None = None) -> SessionHandle:
        storage_state_path: str | None = None
        if username:
            storage_state_path = str(
                ensure_storage_state(
                    browser,
                    base_url=e2e_base_url,
                    auth_dir=auth_artifacts_root,
                    username=username,
                    refresh=os.getenv("E2E_REFRESH_STORAGE_STATE", "").lower() in {"1", "true", "yes"},
                )
            )
        context = browser.new_context(
            base_url=e2e_base_url,
            viewport={"width": 1440, "height": 900},
            storage_state=storage_state_path,
        )
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        artifact_dir = test_artifact_dir / sanitize_name(name)
        page = context.new_page()
        audit = BrowserAudit(page=page, artifact_dir=artifact_dir)
        handle = SessionHandle(context=context, page=page, audit=audit, artifact_dir=artifact_dir)
        sessions.append(handle)
        return handle

    try:
        yield create
    finally:
        for handle in sessions:
            trace_path = handle.artifact_dir / "trace.zip"
            handle.context.tracing.stop(path=str(trace_path))
            handle.context.close()
