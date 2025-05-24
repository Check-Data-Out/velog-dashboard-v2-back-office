import logging

from asgiref.sync import async_to_sync
from django.contrib import admin, messages
from django.db.models import Count, Prefetch, QuerySet
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html

from scraping.main import ScraperTargetUser
from users.models import QRLoginToken, User

logger = logging.getLogger(__name__)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "velog_uuid",
        "email",
        "group_id",
        "is_active",
        "created_at",
        "post_count",
        "get_qr_login_token",
        "get_qr_expires_at",
        "get_qr_is_used",
    ]

    empty_value_display = "-"
    ordering = ["-created_at"]

    actions = ["make_inactive", "update_stats"]

    def get_list_display(self, request):
        list_display = super().get_list_display(request)
        list_display_labels = {  # noqa
            "velog_uuid": "Velog UUID",
            "email": "이메일",
            "group_id": "그룹 ID",
            "is_active": "활성화 여부",
            "created_at": "생성일",
        }
        return list_display

    def get_queryset(self, request: HttpRequest):
        qs = super().get_queryset(request).annotate(post_count=Count("posts"))

        latest_qr_token_prefetch = Prefetch(
            "qr_login_tokens",
            queryset=QRLoginToken.objects.order_by("-created_at"),
            to_attr="prefetched_qr_tokens",
        )

        return qs.prefetch_related(latest_qr_token_prefetch)

    def _get_latest_token(self, obj: User):
        """사용자의 최신 QR 로그인 토큰을 prefetch 된 데이터에서 가져오기"""
        return (
            obj.prefetched_qr_tokens[0] if obj.prefetched_qr_tokens else None
        )

    @admin.display(description="가장 최신 QR 토큰")
    def get_qr_login_token(self, obj: User):
        """사용자의 최신 QR 로그인 토큰 값"""
        latest_token = self._get_latest_token(obj)
        return latest_token.token if latest_token else "-"

    @admin.display(description="QR 만료 시간")
    def get_qr_expires_at(self, obj: User):
        """사용자의 최신 QR 로그인 토큰 만료 시간"""
        latest_token = self._get_latest_token(obj)
        return latest_token.expires_at if latest_token else "-"

    @admin.display(description="QR 사용 여부")
    def get_qr_is_used(self, obj: User):
        """사용자의 최신 QR 로그인 토큰 사용 여부"""
        latest_token = self._get_latest_token(obj)
        return "사용" if latest_token and latest_token.is_used else "미사용"

    @admin.display(description="유저당 게시글 수")
    def post_count(self, obj: User):
        return obj.post_count

    @admin.action(description="선택된 사용자를 비활성화")
    def make_inactive(self, request: HttpRequest, queryset: QuerySet[User]):
        updated = queryset.update(is_active=False)
        logger.info(
            f"{request.user} 가 {updated} 명 사용자를 비활성화 했습니다."
        )
        self.message_user(
            request,
            f"{updated} 명의 사용자가 비활성화되었습니다.",
            messages.SUCCESS,
        )

    @admin.action(
        description="선택된 사용자 실시간 통계 업데이트 (1명 정도만 진행, 이상 timeout 발생 위험)"
    )
    def update_stats(self, request: HttpRequest, queryset: QuerySet[User]):
        user_pk_list = list(queryset.values_list("pk", flat=True))
        logger.info(
            f"{request.user} 가 {user_pk_list} 사용자를 실시간 업데이트 시도 했습니다."
        )

        if len(user_pk_list) >= 3:
            return self.message_user(
                request,
                f"3명 이상의 유저를 선택하지 말아주세요 >> {user_pk_list}",
                messages.ERROR,
            )

        try:
            # 비동기 함수를 동기적으로 실행
            async_to_sync(ScraperTargetUser(user_pk_list).run)()
        except Exception as e:
            return self.message_user(
                request,
                f"실시간 통계 업데이트를 실패했습니다 >> {e}, {e.__class__}",
                messages.ERROR,
            )

        return self.message_user(
            request,
            f"{len(user_pk_list)} 명의 사용자 통계를 실시간 업데이트 성공했습니다.",
            messages.SUCCESS,
        )


@admin.register(QRLoginToken)
class QRLoginTokenAdmin(admin.ModelAdmin):
    list_display = (
        "token",
        "user_link",
        "created_at",
        "expires_at",
        "is_used",
        "ip_address",
        "user_agent",
    )
    list_filter = ("is_used", "expires_at")
    search_fields = ("token", "ip_address")
    ordering = ("-id",)
    readonly_fields = ("token", "created_at")
    actions = ["make_used", "make_unused"]

    @admin.display(description="사용자")
    def user_link(self, obj: QRLoginToken):
        url = reverse("admin:users_user_change", args=[obj.user.id])
        return format_html(
            '<a target="_blank" href="{}" style="min-width: 80px; display: block;">{}</a>',
            url,
            obj.user.email,
        )

    @admin.action(description="선택한 QR 로그인 토큰을 사용 상태로 변경")
    def make_used(self, request, queryset):
        """선택한 QR 로그인 토큰을 '사용됨' 상태로 변경"""
        queryset.update(is_used=True)

    @admin.action(description="선택된 QR 로그인 토큰을 미사용 상태로 변경")
    def make_unused(self, request, queryset):
        """선택한 QR 로그인 토큰을 '미사용' 상태로 변경"""
        queryset.update(is_used=False)
