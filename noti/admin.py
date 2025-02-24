from django.contrib import admin

from noti.models import NotiPost


@admin.register(NotiPost)
class NotiPostAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "author",
        "is_active",
        "created_at",
        "updated_at",
    )
    list_filter = ("is_active", "author", "created_at")
    search_fields = ("title", "content", "author__username")
    ordering = ("-id",)
    actions = ["make_active", "make_inactive"]

    def make_active(self, request, queryset):
        """선택한 공지글을 활성화"""
        queryset.update(is_active=True)

    make_active.short_description = "선택된 공지글 활성화"

    def make_inactive(self, request, queryset):
        """선택한 공지글을 비활성화"""
        queryset.update(is_active=False)

    make_inactive.short_description = "선택된 공지글 비활성화"
