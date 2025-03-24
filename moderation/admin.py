from django.contrib import admin
from moderation.models import ModerationResult, ModerationStatus


@admin.register(ModerationResult)
class ModerationResultAdmin(admin.ModelAdmin):
    list_display = ('id', 'passed', 'created_at', 'manual_status', 'short_reasons')
    list_filter = ('passed', 'manual_status', 'created_at')
    search_fields = ('reasons',)

    def short_reasons(self, obj):
        return (obj.reasons[:50] + "...") if obj.reasons else "—"
