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
from django.contrib import admin
from django.urls import path, include

import core.views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('signup/', core.views.signup, name='signup'),
    path('', core.views.index, name='index'),
    path('add_offer', core.views.add_offer, name='add_offer'),
    path('offer/<int:offer_id>', core.views.offer, name='offer'),
    path('update_offer/<int:offer_id>', core.views.update_offer, name='update_offer'),
    path('delete_offer/<int:offer_id>', core.views.delete_offer, name='delete_offer'),
    path('about', core.views.about, name='about'),
    path('announcement', core.views.announcement, name='announcement'),
    path("__reload__/", include("django_browser_reload.urls")),
]

htmx_urlpatterns = [
    path('offer_search/', core.views.offer_search, name='offer_search'),
    path('offer/<int:offer_id>/contact_info', core.views.offer_contact_info, name='offer_contact_info'),
]

urlpatterns += htmx_urlpatterns