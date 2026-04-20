from django.conf import settings
from django.db import models


class Conversation(models.Model):
    offer = models.ForeignKey(
        'core.Offer', on_delete=models.SET_NULL, null=True, related_name='conversations'
    )
    offer_title = models.CharField(max_length=200, blank=True)
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='conversations')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Conversation #{self.pk}"

    def get_other_participant(self, user):
        return self.participants.exclude(pk=user.pk).first()

    def unread_count_for(self, user):
        return self.messages.filter(read_at__isnull=True).exclude(sender=user).count()

    def last_message(self):
        return self.messages.order_by('-sent_at').first()


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='sent_messages'
    )
    body = models.TextField(max_length=5000)
    sent_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    is_flagged = models.BooleanField(default=False)
    flag_reason = models.TextField(blank=True)
    is_system = models.BooleanField(default=False)

    class Meta:
        ordering = ['sent_at']

    def __str__(self):
        return f"Message #{self.pk} de {self.sender}"
