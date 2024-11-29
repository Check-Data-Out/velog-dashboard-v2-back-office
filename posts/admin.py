from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from posts.models import Post, PostDailyStatistics, PostStatistics


class BasePostRelatedAdmin(admin.ModelAdmin):
    def post_link(self, obj):
        url = reverse("admin:posts_post_change", args=[obj.post.id])
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer" class="admin-link">확인</a>',
            url,
        )

    post_link.short_description = "게시글 정보"


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = [
        "post_uuid",
        "user_link",
        "title",
        "created_at",
        "updated_at",
    ]

    def user_link(self, obj):
        url = reverse("admin:users_user_change", args=[obj.user.id])
        return format_html(
            f'<a target="_blank" href="{{}}" style="min-width: 80px; display: block;">{obj.user.velog_uuid}</a>',
            url,
        )

    user_link.short_description = "사용자"


@admin.register(PostStatistics)
class PostStatisticsAdmin(BasePostRelatedAdmin):
    list_display = [
        "post",
        "post_link",
        "view_count",
        "like_count",
        "created_at",
        "updated_at",
    ]


@admin.register(PostDailyStatistics)
class PostDailyStatisticsAdmin(BasePostRelatedAdmin):
    list_display = [
        "post",
        "post_link",
        "date",
        "daily_view_count",
        "daily_like_count",
        "created_at",
        "updated_at",
    ]
