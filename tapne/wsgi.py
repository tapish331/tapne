# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tapne.settings")

application = get_wsgi_application()
