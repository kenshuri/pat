from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from moderation.models import ModerationResult
from .models import Play, PlayMembership, Representation, Contributor, PublicationCredit, Transaction


class ContributorInline(admin.TabularInline):
    model = Contributor
    extra = 1
    fields = ("role", "name")
    verbose_name = "Contributeur"
    verbose_name_plural = "Contributeurs"


class RepresentationInline(admin.TabularInline):
    model = Representation
    extra = 1
    fields = ("datetime", "venue", "city", "ticket_url")
    ordering = ("datetime",)
    verbose_name = "Représentation"
    verbose_name_plural = "Représentations"


@admin.register(Play)
class PlayAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "genre", "moderation_status", "user", "created_at")
    list_editable = ("moderation_status",)
    search_fields = ("title", "company", "author")
    list_filter = ("moderation_status", "genre", "year_created")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "moderation_preview")
    inlines = [ContributorInline, RepresentationInline]

    fieldsets = (
        (_("Contenu"), {
            "fields": ("title", "author", "company", "genre", "description", "duration", "year_created", "website"),
        }),
        (_("Médias"), {
            "fields": ("poster", "cover_image"),
        }),
        (_("Modération"), {
            "fields": ("moderation_status", "moderation", "moderation_preview"),
        }),
        (_("Métadonnées"), {
            "fields": ("user", "created_at"),
        }),
    )

    actions = ("valider_pieces", "rejeter_pieces")

    @admin.display(description=_("Résumé modération"))
    def moderation_preview(self, obj):
        if not obj.moderation:
            return "—"
        parts = []
        if obj.moderation.reasons:
            parts.append(f"Texte : {obj.moderation.reasons}")
        if obj.moderation.image_reasons:
            parts.append(f"Images : {obj.moderation.image_reasons}")
        return " | ".join(parts) if parts else "✅ Aucun problème détecté"

    @admin.action(description=_("Valider les pièces sélectionnées"))
    def valider_pieces(self, request, queryset):
        updated = queryset.update(moderation_status='published')
        self.message_user(request, _("%d pièce(s) validée(s).") % updated, level=messages.SUCCESS)

    @admin.action(description=_("Rejeter les pièces sélectionnées"))
    def rejeter_pieces(self, request, queryset):
        updated = queryset.update(moderation_status='rejected')
        self.message_user(request, _("%d pièce(s) rejetée(s).") % updated, level=messages.WARNING)


@admin.register(Representation)
class RepresentationAdmin(admin.ModelAdmin):
    list_display = ("play", "datetime", "venue", "city")
    list_filter = ("city",)
    search_fields = ("play__title", "venue", "city")
    ordering = ("-datetime",)


@admin.register(PublicationCredit)
class PublicationCreditAdmin(admin.ModelAdmin):
    list_display = ("user", "remaining_credits")
    search_fields = ("user__username",)


@admin.register(PlayMembership)
class PlayMembershipAdmin(admin.ModelAdmin):
    list_display = ('play', 'email', 'direction', 'status', 'role', 'initiated_by', 'created_at')
    list_filter = ('direction', 'status')
    search_fields = ('email', 'play__title')
    ordering = ('-created_at',)
    readonly_fields = ('token',)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("user", "credits_purchased", "amount", "date")
    list_filter = ("date",)
    search_fields = ("user__username",)
    ordering = ("-date",)
