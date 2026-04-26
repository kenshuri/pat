from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _
from .models import Promote


@admin.register(Promote)
class PromoteAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'title', 'play', 'status', 'formula',
        'start_date', 'end_date', 'price_paid', 'user',
        'impression_count', 'click_count', 'ctr',
    )
    list_filter  = ('status', 'formula', 'start_date')
    search_fields = ('title', 'user__email', 'play__title')
    date_hierarchy = 'start_date'
    ordering = ('-created_at',)
    readonly_fields = (
        'impression_count', 'click_count', 'detail_view_count',
        'booking_click_count', 'duration_display', 'ctr',
        'created_at', 'updated_at',
    )
    prepopulated_fields = {'slug': ('title',)}
    actions = ('marquer_expire',)

    fieldsets = (
        (_('Informations générales'), {
            'fields': (('title', 'slug'), 'user', 'play'),
        }),
        (_('Stripe'), {
            'fields': ('status', 'formula', 'stripe_session_id', 'price_paid'),
        }),
        (_('Période de diffusion'), {
            'fields': (('start_date', 'end_date'), 'duration_display'),
        }),
        (_('Statistiques'), {
            'classes': ('collapse',),
            'fields': (
                ('impression_count', 'click_count', 'ctr'),
                ('detail_view_count', 'booking_click_count'),
            ),
        }),
        (_('Métadonnées'), {
            'classes': ('collapse',),
            'fields': (('created_at', 'updated_at'),),
        }),
    )

    @admin.display(description='Durée (j)')
    def duration_display(self, obj):
        return obj.duration_days

    @admin.display(description='CTR')
    def ctr(self, obj):
        if obj.impression_count:
            return f"{obj.click_count / obj.impression_count * 100:.1f} %"
        return '—'

    @admin.action(description=_('Marquer comme expirées'))
    def marquer_expire(self, request, queryset):
        updated = queryset.update(status='expired')
        self.message_user(
            request, _('%d bandeau(x) marqué(s) comme expiré(s).') % updated,
            level=messages.WARNING,
        )
