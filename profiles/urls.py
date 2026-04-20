from django.urls import path
from . import views

app_name = 'profiles'

urlpatterns = [
    path('mon-compte/',              views.my_account,           name='my_account'),
    path('comedien/editer',          views.actor_edit,          name='actor_edit'),
    path('comedien/supprimer',       views.delete_actor_profile, name='delete_actor_profile'),
    path('comedien/<slug:slug>',     views.actor_detail,         name='actor_detail'),
    path('troupe/editer',            views.troupe_edit,          name='troupe_edit'),
    path('troupe/supprimer',         views.delete_troupe_profile, name='delete_troupe_profile'),
    path('troupe/<slug:slug>',       views.troupe_detail,        name='troupe_detail'),
    path('membre/<int:pk>/',         views.user_detail,  name='user_detail'),
]
