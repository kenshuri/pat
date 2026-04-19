from django.urls import path
from . import views

app_name = 'profiles'

urlpatterns = [
    path('comedien/editer',          views.actor_edit,   name='actor_edit'),
    path('comedien/<slug:slug>',     views.actor_detail, name='actor_detail'),
    path('troupe/editer',            views.troupe_edit,  name='troupe_edit'),
    path('troupe/<slug:slug>',       views.troupe_detail, name='troupe_detail'),
    path('membre/<int:pk>/',         views.user_detail,  name='user_detail'),
]
