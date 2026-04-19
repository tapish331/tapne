from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


def ensure_build_artifact(repo_root: Path) -> None:
    artifact = repo_root / "artifacts" / "lovable-production-dist" / "index.html"
    if not artifact.is_file():
        raise RuntimeError(
            f"Missing production frontend artifact at {artifact}. "
            "Run `pwsh -File infra/build-lovable-production-frontend.ps1` first."
        )


def wait_for_health(base_url: str, *, timeout_seconds: float = 60.0) -> None:
    deadline = time.time() + timeout_seconds
    health_url = f"{base_url.rstrip('/')}/health/"
    last_error = "server did not become healthy"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=5) as response:
                if response.status == 200:
                    return
        except urllib.error.URLError as exc:
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"Django server failed health check at {health_url}: {last_error}")


def resolve_runserver_target(base_url: str) -> str:
    parsed = urlsplit(base_url)
    host = parsed.hostname or "127.0.0.1"
    if parsed.port is not None:
        port = parsed.port
    elif parsed.scheme == "https":
        port = 443
    else:
        port = 80
    return f"{host}:{port}"


def build_server_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("DEBUG", "true")
    env.setdefault("SECRET_KEY", "local-e2e-secret")
    env.setdefault("DATABASE_URL", "sqlite:///test_settings.sqlite3")
    env.setdefault("REDIS_ENABLED", "false")
    env.setdefault("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
    env.setdefault("LOVABLE_FRONTEND_ENABLED", "true")
    env.setdefault("LOVABLE_FRONTEND_REQUIRE_LIVE_DATA", "true")
    env.setdefault("TAPNE_ENABLE_DEMO_DATA", "false")
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


def resolve_python_executable(repo_root: Path) -> str:
    configured = os.getenv("E2E_PYTHON", "").strip()
    if configured:
        return configured

    windows_venv = repo_root / ".venv" / "Scripts" / "python.exe"
    if windows_venv.is_file():
        return str(windows_venv)

    posix_venv = repo_root / ".venv" / "bin" / "python"
    if posix_venv.is_file():
        return str(posix_venv)

    return sys.executable


class DjangoServer:
    def __init__(self, *, repo_root: Path, base_url: str, log_dir: Path) -> None:
        self.repo_root = repo_root
        self.base_url = base_url
        self.log_dir = log_dir
        self.process: subprocess.Popen[str] | None = None

    def start(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = self.log_dir / "django-server.out.log"
        stderr_path = self.log_dir / "django-server.err.log"
        python_executable = resolve_python_executable(self.repo_root)
        runserver_target = resolve_runserver_target(self.base_url)
        env = build_server_env()
        stdout_handle = stdout_path.open("w", encoding="utf-8")
        stderr_handle = stderr_path.open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            [python_executable, "manage.py", "runserver", runserver_target, "--noreload"],
            cwd=self.repo_root,
            env=env,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
        )
        wait_for_health(self.base_url)

    def stop(self) -> None:
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=10)
        self.process = None
