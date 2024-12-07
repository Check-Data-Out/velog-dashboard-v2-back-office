from django.contrib import admin

from tracking.models import UserEventTracking


@admin.register(UserEventTracking)
class UserEventTrackingAdmin(admin.ModelAdmin):
    """사용자 이벤트 추적 어드민"""

    list_display = ("get_user_email", "event_type", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("user__email", "event_type")
    ordering = ("-id",)
    readonly_fields = ("created_at", "user")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")

    @admin.display(ordering="user__email", description="사용자 이메일")
    def get_user_email(self, obj):
        return obj.user.email

    fieldsets = (
        (
            ("이벤트 정보"),
            {
                "fields": (
                    "event_type",
                    "user",
                )
            },
        ),
        (("시간 정보"), {"fields": ("created_at",)}),
    )
