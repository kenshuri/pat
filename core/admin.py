# core/admin.py
import datetime
from django import forms
from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from .models import Offer


# ---- Filtre "Récent" (< 7 j, < 30 j) ----
class RecentFilter(admin.SimpleListFilter):
    title = _("Récence")
    parameter_name = "recent"

    def lookups(self, request, model_admin):
        return (
            ("1w", _("Moins de 7 jours")),
            ("30d", _("Moins de 30 jours")),
        )

    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == "1w":
            return queryset.filter(created_on__gte=now - datetime.timedelta(days=7))
        if self.value() == "30d":
            return queryset.filter(created_on__gte=now - datetime.timedelta(days=30))
        return queryset


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    save_on_top = True
    date_hierarchy = "created_on"
    ordering = ("-created_on",)
    list_select_related = ("author", "moderation")

    # Colonnes de la liste
    list_display = (
        "id", "title", "section", "type", "category",
        "city", "gender", "age_range", "filled",
        "is_recent", "displayed_email", "contact_phone",
        "created_on", "author_display",
        "moderation_status", "moderation_passed",
    )
    list_display_links = ("title",)
    list_editable = ("filled",)

    # Recherche & filtres
    search_fields = (
        "title", "summary", "description", "city",
        "contact_name", "contact_email", "contact_phone", "contact_website",
        "author__username", "author__email",
    )
    list_filter = (
        "section", "type", "category", "gender",
        "filled", "show_author_mail",
        RecentFilter,
        ("created_on", admin.DateFieldListFilter),
        "moderation__manual_status", "moderation__passed",
    )

    # Optimisation FK
    raw_id_fields = ("author", "moderation")
    # (ou utilise autocomplete_fields si tu as configuré les search_fields sur ces modèles)
    # autocomplete_fields = ("author", "moderation")

    # Champs en lecture seule (affichages calculés)
    readonly_fields = ("created_on", "moderation_preview", "displayed_email_link", "contact_website_link")

    # Groupes de champs
    fieldsets = (
        (_("Contenu"), {
            "fields": ("type", "section", "category", "title", "summary", "description")
        }),
        (_("Informations pratiques"), {
            "fields": ("city", "min_age", "max_age", "gender", "filled")
        }),
        (_("Auteur & contacts"), {
            "fields": (
                "author", "show_author_mail",
                "contact_name", "contact_email", "contact_phone", "contact_website", "contact_details",
                "displayed_email_link", "contact_website_link",
            )
        }),
        (_("Modération"), {
            "fields": ("moderation", "moderation_preview")
        }),
        (_("Métadonnées"), {
            "fields": ("created_on",)
        }),
    )

    # Actions rapides
    actions = ("marquer_comme_pourvue", "marquer_comme_ouverte")

    # --------- Helpers d’affichage ---------
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("author", "moderation")

    @admin.display(boolean=True, description=_("Récent (< 7 j)"))
    def is_recent(self, obj):
        return bool(getattr(obj, "recent", False))

    @admin.display(description=_("Âge"))
    def age_range(self, obj):
        mi, mx = obj.min_age, obj.max_age
        if mi and mx:
            return f"{mi}–{mx}"
        if mi:
            return f"{mi}+"
        if mx:
            return f"≤{mx}"
        return "—"

    @admin.display(description=_("Auteur"))
    def author_display(self, obj):
        if obj.author_id:
            full_name = getattr(obj.author, "get_full_name", lambda: "")()
            return full_name or getattr(obj.author, "username", None) or getattr(obj.author, "email", None) or obj.author_id
        return "—"

    @admin.display(description=_("Statut modération"))
    def moderation_status(self, obj):
        if obj.moderation_id and hasattr(obj.moderation, "get_manual_status_display"):
            return obj.moderation.get_manual_status_display()
        return "—"

    @admin.display(boolean=True, description=_("Modération OK"))
    def moderation_passed(self, obj):
        return getattr(obj.moderation, "passed", False) if obj.moderation_id else False

    @admin.display(description=_("Résumé modération"))
    def moderation_preview(self, obj):
        if hasattr(obj, "get_moderation_text"):
            return obj.get_moderation_text()
        return ""

    # Email effectivement affiché (contact_email prioritaire, sinon email auteur si show_author_mail)
    @admin.display(description=_("Email affiché"))
    def displayed_email(self, obj):
        email = None
        if obj.contact_email:
            email = obj.contact_email
        elif obj.show_author_mail and obj.author and getattr(obj.author, "email", None):
            email = obj.author.email
        return email or "—"

    # Versions cliquables pour la fiche (readonly_fields)
    @admin.display(description=_("Email affiché (lien)"))
    def displayed_email_link(self, obj):
        email = self.displayed_email(obj)
        if email and email != "—":
            return format_html('<a href="mailto:{0}">{0}</a>', email)
        return "—"

    @admin.display(description=_("Site de contact (lien)"))
    def contact_website_link(self, obj):
        if obj.contact_website:
            return format_html('<a href="{0}" target="_blank" rel="noopener">{0}</a>', obj.contact_website)
        return "—"

    # --------- Actions ---------
    @admin.action(description=_("Marquer comme pourvue"))
    def marquer_comme_pourvue(self, request, queryset):
        updated = queryset.update(filled=True)
        self.message_user(
            request,
            _("%d offre(s) marquée(s) comme pourvue(s).") % updated,
            level=messages.SUCCESS,
        )

    @admin.action(description=_("Marquer comme ouverte"))
    def marquer_comme_ouverte(self, request, queryset):
        updated = queryset.update(filled=False)
        self.message_user(
            request,
            _("%d offre(s) marquée(s) comme ouverte(s).") % updated,
            level=messages.SUCCESS,
        )
