from django.contrib import admin

from ops_tracking.models import StatsRefreshRequest


@admin.register(StatsRefreshRequest)
class StatsRefreshRequestAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "request_id",
        "user",
        "requested_by",
        "status",
        "retry_count",
        "reclaimed_count",
        "finished_at",
        "created_at",
    ]
    list_filter = ["status", "created_at"]
    search_fields = [
        "request_id",
        "user__id",
        "user__email",
        "requested_by__email",
    ]
    ordering = ["-created_at"]
    readonly_fields = [
        "request_id",
        "user",
        "requested_by",
        "retry_count",
        "reclaimed_count",
        "last_error",
        "finished_at",
        "created_at",
        "updated_at",
    ]
