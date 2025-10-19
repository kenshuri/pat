from django.urls import path
from . import views

app_name = "shows"

urlpatterns = [
    path("agenda/", views.agenda, name="agenda"),
    path("agenda/user/", views.agenda_user, name="agenda-user"),
    path("agenda/filter/", views.agenda_filter, name="agenda-filter"),
    path("play/<int:pk>/", views.play_detail, name="play_detail"),
    path('<int:pk>/add-representation/', views.add_representation, name='add_representation'),
    path("representation/partial/credit", views.get_representation_form_partial_credit, name="get_representation_credit"),
    path("representation/<int:pk>/delete/", views.delete_representation, name="delete_representation"),
    path("play/add/", views.add_play, name="add_play"),
    path("contributors/empty-row/", views.contributor_empty_row, name="contributor_empty_row"),
    path("plays/<int:pk>/edit/", views.edit_play, name="edit_play"),
    path("plays/<int:pk>/delete/", views.delete_play, name="delete_play"),
    path("repertoire/", views.repertoire, name="repertoire"),

]