from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from playwright.sync_api import BrowserContext, Page

from tests.e2e.helpers import BrowserAudit


@dataclass
class SessionHandle:
    context: BrowserContext
    page: Page
    audit: BrowserAudit
    artifact_dir: Path


class SessionFactory(Protocol):
    def __call__(self, *, name: str, username: str | None = None) -> SessionHandle: ...
