from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from posts.models import Post, PostDailyStatistics


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "post_uuid",
        "user_link",
        "title",
        "created_at",
    ]

    def user_link(self, obj):
        url = reverse("admin:users_user_change", args=[obj.user.id])
        return format_html(
            f'<a target="_blank" href="{{}}" style="min-width: 80px; display: block;">{obj.user.velog_uuid}</a>',
            url,
        )

    user_link.short_description = "사용자"


@admin.register(PostDailyStatistics)
class PostDailyStatisticsAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "post_title",
        "date",
        "daily_view_count",
        "daily_like_count",
        "created_at",
    ]
    list_filter = ["date"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("post")

    def post_title(self, obj):
        url = reverse("admin:posts_post_change", args=[obj.post.id])
        return format_html(
            '<a href="{}" target="_blank">{}</a>', url, obj.post.title
        )

    post_title.short_description = "게시글 제목"
