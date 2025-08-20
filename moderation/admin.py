# moderation/admin.py
from django.contrib import admin, messages
from django.db.models import Count, Q
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _

from .models import ModerationResult, ModerationStatus
from moderation.utils import CATEGORY_TRANSLATIONS
from core.models import Offer


# ------------ Filtres personnalisés ------------
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
        # dépend de l'annotation _offers_count faite dans get_queryset
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


# ------------ Inline des offres liées ------------
class OfferInline(admin.TabularInline):
    model = Offer
    fk_name = "moderation"
    fields = ("title", "type", "section", "category", "city", "filled", "created_on")
    readonly_fields = fields
    extra = 0
    can_delete = False
    show_change_link = True
    verbose_name = _("Annonce liée")
    verbose_name_plural = _("Annonces liées")


# ------------ Admin principal ------------
@admin.register(ModerationResult)
class ModerationResultAdmin(admin.ModelAdmin):
    inlines = [OfferInline]

    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    actions_on_top = actions_on_bottom = True

    # Colonnes liste
    list_display = (
        "id",
        "passed",
        "manual_status",
        "created_at",
        "reasons_badges",
        "offers_count",
    )
    list_display_links = ("id",)
    list_editable = ("passed", "manual_status")

    # Recherche & filtres
    search_fields = (
        "reasons",
        "offers__title", "offers__summary", "offers__description",
        "offers__author__username", "offers__author__email",
    )
    list_filter = (
        "passed",
        "manual_status",
        ("created_at", admin.DateFieldListFilter),
        HasReasonsFilter,
        HasOffersFilter,
        ReasonCodeFilter,
    )

    readonly_fields = ("created_at", "reasons_localized_display")
    fieldsets = (
        (_("Statut"), {
            "fields": ("passed", "manual_status", "created_at"),
        }),
        (_("Raisons"), {
            "fields": ("reasons", "reasons_localized_display"),
        }),
    )

    # ---------- Queryset & annotations ----------
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(_offers_count=Count("offers"))

    @admin.display(description=_("Annonces liées"))
    def offers_count(self, obj):
        return getattr(obj, "_offers_count", 0) or 0

    # ---------- Affichages custom ----------
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

    # ---------- Actions ----------
    @admin.action(description=_("Marquer comme ACCEPTÉ (passed=True, statut = Révisé et accepté)"))
    def action_mark_passed(self, request, queryset):
        updated = queryset.update(passed=True, manual_status=ModerationStatus.REVIEW_PASSED)
        self.message_user(request, _("%d élément(s) marqué(s) ACCEPTÉ.") % updated, level=messages.SUCCESS)

    @admin.action(description=_("Marquer comme REJETÉ (passed=False, statut = Révisé et rejeté)"))
    def action_mark_failed(self, request, queryset):
        updated = queryset.update(passed=False, manual_status=ModerationStatus.REVIEW_FAILED)
        self.message_user(request, _("%d élément(s) marqué(s) REJETÉ.") % updated, level=messages.SUCCESS)

    @admin.action(description=_("Marquer comme Non révisé"))
    def action_mark_not_reviewed(self, request, queryset):
        updated = queryset.update(manual_status=ModerationStatus.NOT_REVIEWED)
        self.message_user(request, _("%d élément(s) marqué(s) Non révisé.") % updated, level=messages.SUCCESS)

    @admin.action(description=_("Marquer comme Révision demandée par l’auteur"))
    def action_mark_review_requested(self, request, queryset):
        updated = queryset.update(manual_status=ModerationStatus.REVIEW_REQUESTED)
        self.message_user(request, _("%d élément(s) marqué(s) Révision demandée.") % updated, level=messages.SUCCESS)

    @admin.action(description=_("Synchroniser 'passed' à partir du 'manual_status'"))
    def action_sync_passed_from_status(self, request, queryset):
        updated_passed = updated_failed = 0
        for obj in queryset.only("id", "passed", "manual_status"):
            if obj.manual_status == ModerationStatus.REVIEW_PASSED and not obj.passed:
                obj.passed = True
                obj.save(update_fields=["passed"])
                updated_passed += 1
            elif obj.manual_status == ModerationStatus.REVIEW_FAILED and obj.passed:
                obj.passed = False
                obj.save(update_fields=["passed"])
                updated_failed += 1
        self.message_user(
            request,
            _("Synchronisation effectuée. Passé→True: %(a)d, Passé→False: %(b)d") % {"a": updated_passed, "b": updated_failed},
            level=messages.INFO,
        )

    actions = (
        "action_mark_passed",
        "action_mark_failed",
        "action_mark_not_reviewed",
        "action_mark_review_requested",
        "action_sync_passed_from_status",
    )
