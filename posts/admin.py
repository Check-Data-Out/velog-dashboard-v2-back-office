from django.contrib import admin

from posts.models import Post, PostDailyStatistics, PostStatistics

admin.site.register(Post)
admin.site.register(PostStatistics)
admin.site.register(PostDailyStatistics)
