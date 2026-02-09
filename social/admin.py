from typing import TYPE_CHECKING

from django.contrib import admin

from .models import Bookmark, FollowRelation

if TYPE_CHECKING:
    _BaseFollowRelationAdmin = admin.ModelAdmin[FollowRelation]
    _BaseBookmarkAdmin = admin.ModelAdmin[Bookmark]
else:
    _BaseFollowRelationAdmin = admin.ModelAdmin
    _BaseBookmarkAdmin = admin.ModelAdmin


@admin.register(FollowRelation)
class FollowRelationAdmin(_BaseFollowRelationAdmin):
    list_display = ("id", "follower", "following", "created_at")
    search_fields = ("follower__username", "following__username")
    autocomplete_fields = ("follower", "following")
    ordering = ("-created_at", "-id")
    readonly_fields = ("created_at",)


@admin.register(Bookmark)
class BookmarkAdmin(_BaseBookmarkAdmin):
    list_display = ("id", "member", "target_type", "target_key", "target_label", "created_at")
    list_filter = ("target_type", "created_at")
    search_fields = ("member__username", "target_key", "target_label")
    autocomplete_fields = ("member",)
    ordering = ("-created_at", "-id")
    readonly_fields = ("created_at", "updated_at")
