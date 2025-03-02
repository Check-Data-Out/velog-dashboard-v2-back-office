from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from posts.models import Post, PostDailyStatistics


class UserGroupRangeFilter(admin.SimpleListFilter):
    title = _("유저 그룹")
    parameter_name = "user__group_id"

    def lookups(self, request, model_admin):
        """필터 옵션 정의 (10개 구간)"""
        return [
            ("1-100", "1~100"),
            ("101-200", "101~200"),
            ("201-300", "201~300"),
            ("301-400", "301~400"),
            ("401-500", "401~500"),
            ("501-600", "501~600"),
            ("601-700", "601~700"),
            ("701-800", "701~800"),
            ("801-900", "801~900"),
            ("901-1000", "901~1000"),
        ]

    def queryset(self, request, queryset):
        """선택한 필터에 맞게 queryset 필터링"""
        if self.value():
            start, end = map(int, self.value().split("-"))
            return queryset.filter(
                user__group_id__gte=start, user__group_id__lte=end
            )
        return queryset


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "post_uuid",
        "user_link",
        "title",
        "created_at",
    ]
    search_fields = ["user__id", "user__email"]
    list_filter = [UserGroupRangeFilter]

    def get_queryset(self, request):
        """쿼리셋 최적화: N+1 문제 해결"""
        return super().get_queryset(request).select_related("user")

    @admin.display(description="사용자")
    def user_link(self, obj):
        url = reverse("admin:users_user_change", args=[obj.user.id])
        return format_html(
            '<a target="_blank" href="{}" style="min-width: 80px; display: block;">{}</a>',
            url,
            obj.user.velog_uuid,
        )


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
    list_filter = ["date", UserGroupRangeFilter]
    search_fields = ["post__title", "post__user__id", "post__user__email"]

    def get_queryset(self, request):
        """쿼리셋 최적화: N+1 문제 해결"""
        return (
            super().get_queryset(request).select_related("post", "post__user")
        )

    @admin.display(description="게시글 제목")
    def post_title(self, obj):
        url = reverse("admin:posts_post_change", args=[obj.post.id])
        return format_html(
            '<a href="{}" target="_blank">{}</a>', url, obj.post.title
        )
