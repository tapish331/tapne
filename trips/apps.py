from importlib import import_module

from django.apps import AppConfig


class TripsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "trips"
    verbose_name = "Trips"

    def ready(self) -> None:
        # Register model signal handlers for banner file cleanup.
        import_module("trips.signals")
