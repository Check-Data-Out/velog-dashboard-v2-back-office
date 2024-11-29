from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from posts.models import Post, PostDailyStatistics, PostStatistics


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = [
        "post_uuid",
        "get_user",
        "title",
        "created_at",
        "updated_at",
    ]

    def get_user(self, obj):
        return format_html(
            f'<a target="_blank" href="{{}}" style="min-width: 80px; display: block;">{obj.user.velog_uuid}</a>',
            f"{reverse('admin:users_user_change', args=[obj.user.id])}",
        )

    get_user.short_description = "사용자"


@admin.register(PostStatistics)
class PostStatisticsAdmin(admin.ModelAdmin):
    list_display = [
        "post",
        "get_post_info",
        "view_count",
        "like_count",
        "created_at",
        "updated_at",
    ]

    def get_post_info(self, obj):
        return format_html(
            '<a target="_blank" href="{}" style="min-width: 80px; display: block;">확인</a>',
            f"{reverse('admin:posts_post_change', args=[obj.post.id])}",
        )

    get_post_info.short_description = "게시글 정보"


@admin.register(PostDailyStatistics)
class PostDailyStatisticsAdmin(admin.ModelAdmin):
    list_display = [
        "post",
        "get_post_info",
        "date",
        "daily_view_count",
        "daily_like_count",
        "created_at",
        "updated_at",
    ]

    def get_post_info(self, obj):
        return format_html(
            '<a target="_blank" href="{}" style="min-width: 80px; display: block;">확인</a>',
            f"{reverse('admin:posts_post_change', args=[obj.post.id])}",
        )

    get_post_info.short_description = "게시글 정보"
