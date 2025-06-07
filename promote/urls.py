from django.urls import path

import promote.views
from . import views     # assumes you already have views.py with PromoteDetailView

app_name = "promote"

urlpatterns = [
    # /promote/romeo-et-juliette/
    path("promote/<slug:slug>/", views.PromoteDetailView.as_view(), name="detail"),
    # clic sur le bandeau (incrémente + redirige vers la page détail)
    path("promote/<slug:slug>/click/", views.banner_click, name="banner_click"),
    path("promote/<slug:slug>/book/", views.booking_redirect, name="booking_redirect"),
    path("promote/", promote.views.default, name="default"),
]
