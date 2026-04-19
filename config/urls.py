"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import os

from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import path, include
from django.views.generic import TemplateView

import core.views
from core.sitemaps import CitySitemap, DepartmentSitemap, OfferSitemap, StaticSitemap
from shows.sitemaps import PlaySitemap

sitemaps = {
    'annonces': OfferSitemap,
    'villes': CitySitemap,
    'departements': DepartmentSitemap,
    'pieces': PlaySitemap,
    'pages': StaticSitemap,
}

urlpatterns = [
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain')),
    path('llms.txt', TemplateView.as_view(template_name='llms.txt', content_type='text/plain')),
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('signup/', core.views.signup, name='signup'),
    path("shows/", include("shows.urls", namespace="shows")),
    path("", include("profiles.urls", namespace="profiles")),
    path('', core.views.index, name='index'),
    path('add_offer', core.views.add_offer, name='add_offer'),
    path('offer/<int:offer_id>', core.views.offer, name='offer'),
    path('offer_user/', core.views.offer_user, name='offer_user'),
    path('update_offer/<int:offer_id>', core.views.update_offer, name='update_offer'),
    path('fill_offer/<int:offer_id>', core.views.fill_offer, name='fill_offer'),
    path('unfill_offer/<int:offer_id>', core.views.unfill_offer, name='unfill_offer'),
    path('delete_offer/<int:offer_id>', core.views.delete_offer, name='delete_offer'),
    path('annonces/', core.views.city_list, name='city_list'),
    path('annonces/<slug:city_slug>', core.views.city_offers, name='city_offers'),
    path('departements/', core.views.department_list, name='department_list'),
    path('departements/<slug:dept_slug>', core.views.department_offers, name='department_offers'),
    path('about', core.views.about, name='about'),
    path('tou', core.views.tou, name='tou'),
    path('announcement', core.views.announcement, name='announcement'),
    path('alertes', core.views.alert, name='alert'),
    path('alertes/mes-alertes', core.views.alert_user, name='alert_user'),
    path('alertes/confirmer/<uuid:token>', core.views.alert_confirm, name='alert_confirm'),
    path('alertes/desactiver/<uuid:token>', core.views.alert_unsubscribe, name='alert_unsubscribe'),
    path('alertes/gerer/<uuid:token>', core.views.alert_manage, name='alert_manage'),
    path('alert', core.views.alert, name='alert_legacy'),
    path("", include("promote.urls", namespace="promote")),
    path("__reload__/", include("django_browser_reload.urls")),
]

htmx_urlpatterns = [
    path('offer_search/', core.views.offer_search, name='offer_search'),
    path('offer/<int:offer_id>/contact_info', core.views.offer_contact_info, name='offer_contact_info'),
    path('offers/<int:page>', core.views.offers, name='offers'),
]

urlpatterns += htmx_urlpatterns

DEBUG = os.environ.get("DJANGO_DEBUG") == 'True'
if DEBUG:
    from debug_toolbar.toolbar import debug_toolbar_urls
    from django.conf import settings
    from django.conf.urls.static import static
    urlpatterns += debug_toolbar_urls()
    urlpatterns += static(settings.MEDIA_URL, document_root=getattr(settings, 'MEDIA_ROOT', None))