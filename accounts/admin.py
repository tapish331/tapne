from django.contrib import admin
from typing import TYPE_CHECKING

from .models import AccountProfile

if TYPE_CHECKING:
    AccountProfileAdminBase = admin.ModelAdmin[AccountProfile]
else:
    AccountProfileAdminBase = admin.ModelAdmin


@admin.register(AccountProfile)
class AccountProfileAdmin(AccountProfileAdminBase):
    list_display = ("user", "display_name", "location", "updated_at")
    search_fields = ("user__username", "user__email", "display_name", "location")
    list_select_related = ("user",)
