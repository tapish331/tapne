from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class AccountProfile(models.Model):
    """
    Profile data that extends the built-in Django user model.

    The app keeps authentication on django.contrib.auth.User and stores
    profile-only fields in this table.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="account_profile",
    )
    display_name = models.CharField(max_length=120, blank=True)
    bio = models.TextField(blank=True, default="")
    location = models.CharField(max_length=120, blank=True)
    website = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("user__username",)

    def __str__(self) -> str:
        return f"@{self.user.get_username()} profile"

    @property
    def effective_display_name(self) -> str:
        if self.display_name:
            return self.display_name

        full_name = self.user.get_full_name().strip()
        if full_name:
            return full_name

        return self.user.get_username()


def ensure_profile(user: Any) -> AccountProfile:
    """
    Guarantee a profile row for the given user.

    This is used by views/commands to avoid repeating get_or_create logic.
    """

    profile, _ = AccountProfile.objects.get_or_create(user=user)
    return profile


UserModel = get_user_model()


@receiver(post_save, sender=UserModel)
def create_profile_for_new_user(sender, instance, created, **kwargs) -> None:  # type: ignore[no-untyped-def]
    # Keep account/profile creation consistent for every signup path.
    if created:
        ensure_profile(instance)
