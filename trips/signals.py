from __future__ import annotations

from typing import Any

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import Trip


def _normalized_file_name(file_field: object) -> str:
    return str(getattr(file_field, "name", "") or "").strip()


def _delete_file_if_unreferenced(*, file_name: str, storage: object, exclude_pk: int | None = None) -> None:
    normalized_name = str(file_name or "").strip()
    if not normalized_name:
        return

    queryset = Trip.objects.filter(banner_image=normalized_name)
    if exclude_pk is not None and exclude_pk > 0:
        queryset = queryset.exclude(pk=exclude_pk)
    if queryset.exists():
        return

    delete_fn = getattr(storage, "delete", None)
    if not callable(delete_fn):
        return

    try:
        delete_fn(normalized_name)
    except Exception:
        # Keep CRUD resilient even if storage delete fails.
        return


@receiver(pre_save, sender=Trip)
def track_replaced_trip_banner_file(sender: type[Trip], instance: Trip, **kwargs: Any) -> None:
    if not instance.pk:
        return

    old_row = Trip.objects.only("id", "banner_image").filter(pk=instance.pk).first()
    if old_row is None:
        return

    old_name = _normalized_file_name(old_row.banner_image)
    new_name = _normalized_file_name(instance.banner_image)
    if not old_name or old_name == new_name:
        return

    setattr(instance, "_old_banner_name_for_cleanup", old_name)
    setattr(instance, "_old_banner_storage_for_cleanup", old_row.banner_image.storage)


@receiver(post_save, sender=Trip)
def cleanup_replaced_trip_banner_file(sender: type[Trip], instance: Trip, **kwargs: Any) -> None:
    old_name = str(getattr(instance, "_old_banner_name_for_cleanup", "") or "").strip()
    if not old_name:
        return

    old_storage = getattr(instance, "_old_banner_storage_for_cleanup", None)
    if old_storage is None:
        old_storage = getattr(instance.banner_image, "storage", None)
    if old_storage is None:
        return

    _delete_file_if_unreferenced(
        file_name=old_name,
        storage=old_storage,
        exclude_pk=int(instance.pk or 0),
    )


@receiver(post_delete, sender=Trip)
def cleanup_deleted_trip_banner_file(sender: type[Trip], instance: Trip, **kwargs: Any) -> None:
    banner_name = _normalized_file_name(instance.banner_image)
    if not banner_name:
        return

    storage = getattr(instance.banner_image, "storage", None)
    if storage is None:
        return

    _delete_file_if_unreferenced(file_name=banner_name, storage=storage)
