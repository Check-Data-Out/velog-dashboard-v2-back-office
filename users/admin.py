from django.contrib import admin

from users.models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = [
        "velog_uuid",
        "access_token",
        "refresh_token",
        "group_id",
        "email",
        "is_active",
        "created_at",
        "updated_at",
    ]
