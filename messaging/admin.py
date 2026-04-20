from django.contrib import admin
from django.utils.html import format_html

from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ('sender', 'body', 'sent_at', 'read_at', 'is_flagged', 'flag_reason', 'is_system')
    can_delete = False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'offer', 'participants_display', 'created_at', 'updated_at')
    list_select_related = ('offer',)
    inlines = [MessageInline]

    def participants_display(self, obj):
        return ' / '.join(u.email for u in obj.participants.all())
    participants_display.short_description = 'Participants'


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation', 'sender', 'short_body', 'sent_at', 'is_flagged', 'flag_reason', 'is_system')
    list_filter = ('is_flagged', 'is_system')
    search_fields = ('body', 'sender__email', 'flag_reason')
    readonly_fields = ('conversation', 'sender', 'body', 'sent_at', 'read_at', 'is_system')
    actions = ['unflag_messages']

    def short_body(self, obj):
        return obj.body[:80] + '…' if len(obj.body) > 80 else obj.body
    short_body.short_description = 'Contenu'

    def unflag_messages(self, request, queryset):
        queryset.update(is_flagged=False, flag_reason='')
    unflag_messages.short_description = 'Lever le signalement'
