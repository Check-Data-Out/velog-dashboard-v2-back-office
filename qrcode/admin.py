from django.contrib import admin

from qrcode.models import QRLoginToken


@admin.register(QRLoginToken)
class QRLoginTokenAdmin(admin.ModelAdmin):
    list_display = (
        "token",
        "user",
        "created_at",
        "expires_at",
        "is_used",
        "ip_address",
        "user_agent",
    )
    list_filter = ("is_used", "expires_at", "user")
    search_fields = ("token", "user__username", "ip_address")
    ordering = ("-created_at",)
    readonly_fields = ("token", "created_at")
    actions = ["make_used", "make_unused"]

    def make_used(self, request, queryset):
        """선택한 QR 로그인 토큰을 '사용됨' 상태로 변경"""
        queryset.update(is_used=True)

    make_used.short_description = "선택된 QR 로그인 토큰을 사용 처리"

    def make_unused(self, request, queryset):
        """선택한 QR 로그인 토큰을 '미사용' 상태로 변경"""
        queryset.update(is_used=False)

    make_unused.short_description = "선택된 QR 로그인 토큰을 미사용 처리"
