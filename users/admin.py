import logging

from django.contrib import admin, messages
from django.db.models import Count, Prefetch, QuerySet
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html

from consumer.envelope import build_envelope
from ops_tracking.models import StatsRefreshRequest
from ops_tracking.services import RequestLifecycleService
from queue_monitor.services import QueueMonitorService
from users.models import QRLoginToken, User

logger = logging.getLogger(__name__)

_MAX_UPDATE_STATS_SELECTION = 10


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "velog_uuid",
        "email",
        "group_id",
        "is_active",
        "newsletter_subscribed",
        "created_at",
        "post_count",
        "get_qr_login_token",
        "get_qr_expires_at",
        "get_qr_is_used",
    ]

    empty_value_display = "-"
    ordering = ["-created_at"]

    actions = ["make_inactive", "update_stats", "make_unsubscribed"]

    def get_list_display(self, request):
        list_display = super().get_list_display(request)
        list_display_labels = {  # noqa
            "velog_uuid": "Velog UUID",
            "email": "이메일",
            "group_id": "그룹 ID",
            "is_active": "활성화 여부",
            "newsletter_subscribed": "뉴스레터 구독 여부",
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

    @admin.action(description="선택된 사용자 뉴스레터 구독 해제")
    def make_unsubscribed(
        self, request: HttpRequest, queryset: QuerySet[User]
    ):
        updated = queryset.update(newsletter_subscribed=False)
        logger.info(
            f"{request.user} 가 {updated} 명 사용자를 뉴스레터 구독 해제 했습니다."
        )
        self.message_user(
            request,
            f"{updated} 명의 사용자가 뉴스레터 구독 해제되었습니다.",
            messages.SUCCESS,
        )

    @admin.action(
        description="선택된 사용자 통계 업데이트 요청 (큐에 추가, 진행은 Queue Monitor 에서 확인)"
    )
    def update_stats(self, request: HttpRequest, queryset: QuerySet[User]):
        """선택된 사용자 통계 업데이트를 큐에 추가한다.

        - max 10명 선택 제한
        - QUEUED/PROCESSING 으로 이미 진행 중인 사용자는 스킵
        - 각 user 에 대해 envelope 생성 + pending 큐 LPUSH + StatsRefreshRequest 생성
        """
        user_pk_list = list(queryset.values_list("pk", flat=True))
        logger.info(
            f"{request.user} 가 {user_pk_list} 사용자 통계 업데이트를 큐에 요청했습니다."
        )

        if len(user_pk_list) > _MAX_UPDATE_STATS_SELECTION:
            return self.message_user(
                request,
                f"{_MAX_UPDATE_STATS_SELECTION} 명 이하로 선택해주세요.",
                messages.ERROR,
            )

        lifecycle = RequestLifecycleService()

        # request.user 는 Django auth.User 이고 StatsRefreshRequest.requested_by 는
        # users.User FK 이므로 email 매칭으로 users.User id 를 찾아 보조. 매칭 실패 시 None.
        requester_id = None
        requester_email = getattr(request.user, "email", None)
        if requester_email:
            requester_id = (
                User.objects.filter(email=requester_email)
                .values_list("id", flat=True)
                .first()
            )

        service = QueueMonitorService()
        queued = 0
        inflight_skipped = 0
        failed = 0
        for user_id in user_pk_list:
            envelope = build_envelope(
                user_id=user_id, requested_by=requester_id
            )
            # try_mark_queued_if_no_inflight: user_id 원자 가드.
            # 동시 요청 race 에서 두 번째 호출은 None 반환 → 중복 enqueue 차단.
            row = lifecycle.try_mark_queued_if_no_inflight(
                request_id=envelope["requestId"],
                user_id=user_id,
                requested_by=requester_id,
            )
            if row is None:
                inflight_skipped += 1
                continue
            try:
                service.redis_client.enqueue_message(envelope)
            except Exception as e:
                logger.error(
                    f"update_stats: enqueue 실패 (user={user_id}): {e}"
                )
                StatsRefreshRequest.objects.filter(
                    request_id=envelope["requestId"]
                ).delete()
                failed += 1
                continue
            queued += 1

        parts = [f"{queued}건 큐에 추가됨"]
        if inflight_skipped:
            parts.append(f"{inflight_skipped}건은 이미 진행중이어서 스킵")
        if failed:
            parts.append(f"{failed}건은 Redis enqueue 실패")
        msg = ", ".join(parts) + ". 진행 상황은 Queue Monitor 에서 확인하세요."
        level = messages.ERROR if failed else messages.SUCCESS
        return self.message_user(request, msg, level)


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
