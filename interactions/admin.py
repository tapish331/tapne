from typing import TYPE_CHECKING

from django.contrib import admin

from .models import Comment, DirectMessage, DirectMessageThread

if TYPE_CHECKING:
    _BaseCommentAdmin = admin.ModelAdmin[Comment]
    _BaseDirectMessageThreadAdmin = admin.ModelAdmin[DirectMessageThread]
    _BaseDirectMessageAdmin = admin.ModelAdmin[DirectMessage]
else:
    _BaseCommentAdmin = admin.ModelAdmin
    _BaseDirectMessageThreadAdmin = admin.ModelAdmin
    _BaseDirectMessageAdmin = admin.ModelAdmin


@admin.register(Comment)
class CommentAdmin(_BaseCommentAdmin):
    list_display = (
        "id",
        "author",
        "target_type",
        "target_key",
        "parent",
        "created_at",
    )
    list_filter = ("target_type", "created_at")
    search_fields = ("author__username", "target_key", "target_label", "text")
    autocomplete_fields = ("author", "parent")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at", "-id")


@admin.register(DirectMessageThread)
class DirectMessageThreadAdmin(_BaseDirectMessageThreadAdmin):
    list_display = ("id", "member_one", "member_two", "updated_at", "created_at")
    search_fields = (
        "member_one__username",
        "member_two__username",
    )
    autocomplete_fields = ("member_one", "member_two")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-updated_at", "-id")


@admin.register(DirectMessage)
class DirectMessageAdmin(_BaseDirectMessageAdmin):
    list_display = ("id", "thread", "sender", "created_at")
    list_filter = ("created_at",)
    search_fields = ("thread__member_one__username", "thread__member_two__username", "sender__username", "body")
    autocomplete_fields = ("thread", "sender")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at", "-id")
