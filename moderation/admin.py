# moderation/admin.py
from django.contrib import admin
from django.db.models import Count, Q
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _

from .models import ModerationResult
from moderation.utils import CATEGORY_TRANSLATIONS
from core.models import Offer


class HasReasonsFilter(admin.SimpleListFilter):
    title = _("Raisons présentes")
    parameter_name = "has_reasons"

    def lookups(self, request, model_admin):
        return (("yes", _("Oui")), ("no", _("Non")))

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.exclude(Q(reasons__isnull=True) | Q(reasons__exact=""))
        if self.value() == "no":
            return queryset.filter(Q(reasons__isnull=True) | Q(reasons__exact=""))
        return queryset


class HasOffersFilter(admin.SimpleListFilter):
    title = _("Liée à au moins 1 annonce")
    parameter_name = "has_offers"

    def lookups(self, request, model_admin):
        return (("yes", _("Oui")), ("no", _("Non")))

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(_offers_count__gt=0)
        if self.value() == "no":
            return queryset.filter(_offers_count__exact=0)
        return queryset


class ReasonCodeFilter(admin.SimpleListFilter):
    title = _("Raison (code)")
    parameter_name = "reason_code"

    def lookups(self, request, model_admin):
        return tuple((k, f"{k} — {CATEGORY_TRANSLATIONS.get(k, k)}")
                     for k in sorted(CATEGORY_TRANSLATIONS.keys()))

    def queryset(self, request, queryset):
        code = self.value()
        if code:
            return queryset.filter(reasons__icontains=code)
        return queryset


class OfferInline(admin.TabularInline):
    model = Offer
    fk_name = "moderation"
    fields = ("title", "type", "section", "city", "moderation_status", "filled", "created_on")
    readonly_fields = fields
    extra = 0
    can_delete = False
    show_change_link = True
    verbose_name = _("Annonce liée")
    verbose_name_plural = _("Annonces liées")


@admin.register(ModerationResult)
class ModerationResultAdmin(admin.ModelAdmin):
    inlines = [OfferInline]

    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    actions_on_top = actions_on_bottom = True

    list_display = (
        "id",
        "text_passed",
        "images_passed",
        "created_at",
        "reasons_badges",
        "offers_count",
    )
    list_display_links = ("id",)

    search_fields = (
        "reasons",
        "offers__title", "offers__summary",
        "offers__author__username", "offers__author__email",
    )
    list_filter = (
        ("created_at", admin.DateFieldListFilter),
        HasReasonsFilter,
        HasOffersFilter,
        ReasonCodeFilter,
    )

    readonly_fields = ("created_at", "text_passed", "reasons_localized_display")
    fieldsets = (
        (_("Résultat texte"), {
            "fields": ("text_passed", "reasons", "reasons_localized_display"),
        }),
        (_("Résultat images"), {
            "fields": ("images_passed", "image_reasons"),
        }),
        (_("Métadonnées"), {
            "fields": ("created_at",),
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(_offers_count=Count("offers"))

    @admin.display(description=_("Annonces liées"))
    def offers_count(self, obj):
        return getattr(obj, "_offers_count", 0) or 0

    @admin.display(boolean=True, description=_("Texte OK"))
    def text_passed(self, obj):
        return not obj.reasons

    @admin.display(description=_("Raisons (localisées)"))
    def reasons_localized_display(self, obj):
        items = obj.get_localized_reasons()
        if not items:
            return "—"
        return format_html(
            "<ul style='margin:0;padding-left:16px;'>{}</ul>",
            format_html_join("", "<li>{}</li>", ((it,) for it in items))
        )

    @admin.display(description=_("Raisons"))
    def reasons_badges(self, obj):
        items = obj.get_localized_reasons()
        if not items:
            return "—"
        html = format_html_join(
            " ",
            "<span style='display:inline-block;padding:2px 8px;border:1px solid #bbb;border-radius:999px;'>{}</span>",
            ((it,) for it in items[:6])
        )
        return html + (format_html(" …") if len(items) > 6 else html.__class__(""))
