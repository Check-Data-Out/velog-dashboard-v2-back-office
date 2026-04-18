"""Queue Monitor Admin — AdminSite 커스텀 URL 패턴.

Redis 상태는 DB 가 아니므로 Proxy Model 대신 AdminSite 의 ``get_urls()`` 를
확장해 큐 대시보드/DLQ 뷰를 등록한다.

URL:
    /admin/queue/dashboard/
    /admin/queue/failed/
    /admin/queue/failed/retry/<request_id>/
    /admin/queue/failed/purge/
"""

import logging

from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import URLPattern, URLResolver, path, reverse

from queue_monitor.services import QueueMonitorService

logger = logging.getLogger(__name__)


def dashboard_view(request: HttpRequest) -> HttpResponse:
    service = QueueMonitorService()
    stats = service.get_queue_stats()
    context = {
        **admin.site.each_context(request),
        "title": "Queue Monitor",
        "stats": stats,
    }
    return TemplateResponse(
        request, "admin/queue_monitor/dashboard.html", context
    )


def failed_list_view(request: HttpRequest) -> HttpResponse:
    service = QueueMonitorService()
    try:
        offset = max(int(request.GET.get("offset", 0)), 0)
    except ValueError:
        offset = 0
    try:
        limit = min(max(int(request.GET.get("limit", 50)), 1), 200)
    except ValueError:
        limit = 50

    total = service.get_queue_stats()["failed"]
    items = service.get_failed_messages(offset=offset, limit=limit)
    context = {
        **admin.site.each_context(request),
        "title": "Queue Monitor - Failed (DLQ)",
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
        "next_offset": offset + limit if offset + limit < total else None,
        "prev_offset": max(offset - limit, 0) if offset > 0 else None,
    }
    return TemplateResponse(
        request, "admin/queue_monitor/failed_messages.html", context
    )


def retry_view(request: HttpRequest, request_id: str) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseRedirect(reverse("admin:queue_failed_list"))
    service = QueueMonitorService()
    ok = service.retry_failed_message(request_id)
    if ok:
        messages.success(request, f"DLQ 재시도 완료: {request_id}")
    else:
        messages.warning(
            request, f"DLQ 재시도 실패 (requestId 미발견): {request_id}"
        )
    return HttpResponseRedirect(reverse("admin:queue_failed_list"))


def purge_confirm_view(request: HttpRequest) -> HttpResponse:
    service = QueueMonitorService()
    if request.method == "POST" and request.POST.get("confirm") == "yes":
        count = service.purge_failed()
        messages.success(request, f"DLQ 퍼지 완료 ({count}건)")
        return HttpResponseRedirect(reverse("admin:queue_dashboard"))
    # GET 또는 confirm 누락 시 확인 페이지 렌더
    context = {
        **admin.site.each_context(request),
        "title": "DLQ 전체 삭제 확인",
        "failed_count": service.get_queue_stats()["failed"],
    }
    return TemplateResponse(
        request, "admin/queue_monitor/purge_confirm.html", context
    )


_original_get_urls = admin.site.get_urls


def _patched_get_urls() -> list[URLPattern | URLResolver]:
    custom = [
        path(
            "queue/dashboard/",
            admin.site.admin_view(dashboard_view),
            name="queue_dashboard",
        ),
        path(
            "queue/failed/",
            admin.site.admin_view(failed_list_view),
            name="queue_failed_list",
        ),
        path(
            "queue/failed/retry/<str:request_id>/",
            admin.site.admin_view(retry_view),
            name="queue_retry",
        ),
        path(
            "queue/failed/purge/",
            admin.site.admin_view(purge_confirm_view),
            name="queue_purge",
        ),
    ]
    return custom + _original_get_urls()


admin.site.get_urls = _patched_get_urls  # type: ignore[assignment]
