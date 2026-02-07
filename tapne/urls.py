# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from django.contrib import admin
from django.http import HttpRequest, JsonResponse
from django.urls import URLPattern, URLResolver, path


def health(_request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok", "service": "tapne-placeholder"})


urlpatterns: list[URLPattern | URLResolver] = [
    path("", health, name="health"),
    path("admin/", admin.site.urls),
]
