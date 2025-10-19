from django.contrib import admin
from .models import Play, Representation, Contributor, PublicationCredit, Transaction


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
    list_display = ("title", "company", "genre", "year_created", "user", "created_at")
    search_fields = ("title", "company", "author")
    list_filter = ("genre", "year_created")
    ordering = ("-created_at",)
    inlines = [ContributorInline, RepresentationInline]


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


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("user", "credits_purchased", "amount", "date")
    list_filter = ("date",)
    search_fields = ("user__username",)
    ordering = ("-date",)
