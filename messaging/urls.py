from django.urls import path
from . import views

app_name = 'messaging'

urlpatterns = [
    path('messages/', views.inbox, name='inbox'),
    path('messages/<int:pk>/', views.conversation_detail, name='conversation'),
    path('messages/nouveau/<int:offer_id>/', views.new_conversation, name='new_conversation'),
    path('messages/message/<int:message_id>/signaler/', views.report_message, name='report_message'),
    path('messages/<int:conv_id>/reveler-email/', views.reveal_email, name='reveal_email'),
]
