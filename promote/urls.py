from django.urls import path
from django.views.decorators.csrf import csrf_exempt

import promote.views
from . import views

app_name = "promote"

urlpatterns = [
    # --- self-service sponsor (must be BEFORE slug catch-all) ---
    path("promote/sponsor/", views.sponsor_list, name="sponsor_list"),
    path("promote/sponsor/calendar/", views.sponsor_calendar, name="sponsor_calendar"),
    path("promote/sponsor/availability/", views.sponsor_availability, name="sponsor_availability"),
    path("promote/sponsor/checkout/<int:play_id>/", views.sponsor_checkout, name="sponsor_checkout"),
    path("promote/sponsor/confirmation/<str:session_id>/", views.sponsor_confirmation, name="sponsor_confirmation"),
    path("promote/sponsor/cancel/", views.sponsor_cancel, name="sponsor_cancel"),
    path("promote/sponsor/webhook/", csrf_exempt(views.stripe_webhook), name="stripe_webhook"),

    # --- legacy slug-based banner (catch-all, must be LAST) ---
    path("promote/<slug:slug>/", views.PromoteDetailView.as_view(), name="detail"),
    path("promote/<slug:slug>/click/", views.banner_click, name="banner_click"),
    path("promote/<slug:slug>/book/", views.booking_redirect, name="booking_redirect"),
    path("promote/", promote.views.default, name="default"),
]
