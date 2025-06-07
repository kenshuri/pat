# apps/promote/admin.py
from django.contrib import admin
from django.utils.html import format_html
from .models import Promote


@admin.register(Promote)
class PromoteAdmin(admin.ModelAdmin):
    # ▸ liste des colonnes affichées dans l’index
    list_display = (
        "id",
        "title",
        "user",
        "start_date",
        "end_date",
        "duration_display",
        "price_paid",
        "impression_count",
        "click_count",
        "ctr",
        "booking_click_count",
    )
    list_filter = ("start_date", "end_date", "price_paid")
    search_fields = ("title", "user__username", "user__email")
    date_hierarchy = "start_date"
    ordering = ("-created_at",)

    # ▸ champs en lecture seule (pas d’édition manuelle)
    readonly_fields = (
        "impression_count",
        "click_count",
        "detail_view_count",
        "booking_click_count",
        "duration_display",
        "ctr",
        "created_at",
        "updated_at",
    )

    # ▸ slug pré-rempli côté admin
    prepopulated_fields = {"slug": ("title",)}

    # ▸ organisation visuelle du formulaire
    fieldsets = (
        (
            "Informations générales",
            {
                "fields": (
                    ("title", "slug"),
                    "user",
                )
            },
        ),
        (
            "Période de diffusion",
            {
                "fields": (
                    ("start_date", "end_date"),
                    "duration_display",
                )
            },
        ),
        (
            "Statistiques (lecture seule)",
            {
                "classes": ("collapse",),
                "fields": (
                    ("impression_count", "click_count", "ctr"),
                    ("detail_view_count", "booking_click_count"),
                ),
            },
        ),
        (
            "Facturation",
            {
                "fields": ("price_paid",),
            },
        ),
        (
            "Métadonnées",
            {
                "classes": ("collapse",),
                "fields": (("created_at", "updated_at"),),
            },
        ),
    )

    # ▸ méthode utilitaire pour afficher la durée en jours
    @admin.display(description="Durée (j)")
    def duration_display(self, obj):
        return obj.duration_days

    # ▸ CTR calculé à la volée
    @admin.display(description="CTR")
    def ctr(self, obj):
        if obj.impression_count:
            pct = obj.click_count / obj.impression_count * 100
            return f"{pct:.1f} %"
        return "—"
