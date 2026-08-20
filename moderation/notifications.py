"""Notification de l'auteur quand un modérateur publie ou rejette son contenu.

Une publication automatique (tâche Celery) ne notifie jamais l'auteur : seule une
décision humaine déclenche un email.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

logger = logging.getLogger(__name__)

PUBLISHED = 'published'
REJECTED = 'rejected'
NOTIFIED_STATUSES = (PUBLISHED, REJECTED)


def _site_url():
    return getattr(settings, 'SITE_URL', 'https://petites-annonces-theatre.fr')


def notify_offer_decision(offer, previous_status):
    """Prévient l'auteur d'une annonce du sort réservé à sa publication."""
    return _notify_decision(
        recipient=getattr(offer.author, 'email', None) if offer.author else None,
        previous_status=previous_status,
        new_status=offer.moderation_status,
        title=offer.title,
        label="votre annonce",
        url=f"{_site_url()}{reverse('offer', args=[offer.pk])}",
        moderation=offer.moderation,
    )


def notify_play_decision(play, previous_status):
    """Prévient le propriétaire d'une pièce du sort réservé à sa publication."""
    return _notify_decision(
        recipient=getattr(play.user, 'email', None) if play.user else None,
        previous_status=previous_status,
        new_status=play.moderation_status,
        title=play.title,
        label="votre pièce",
        url=f"{_site_url()}{reverse('shows:play_detail', args=[play.pk])}",
        moderation=play.moderation,
    )


def _notify_decision(*, recipient, previous_status, new_status, title, label, url, moderation):
    """Envoie l'email si — et seulement si — une décision vient d'être prise.

    Retourne True si un email est parti.
    """
    if new_status not in NOTIFIED_STATUSES:
        return False
    if previous_status == new_status:
        # Re-sauvegarde sans changement de statut : pas de doublon.
        return False
    if not recipient:
        return False

    published = new_status == PUBLISHED
    reasons = moderation.get_localized_reasons() if moderation and not published else []

    if published:
        subject = f"{label.capitalize()} « {title} » est en ligne"
    else:
        subject = f"{label.capitalize()} « {title} » n'a pas été publiée"

    context = {
        'published': published,
        'title': title,
        'label': label,
        'url': url,
        'reasons': reasons,
    }
    html_body = render_to_string('emails/moderation_decision.html', context)
    text_body = render_to_string('emails/moderation_decision.txt', context)

    try:
        send_mail(
            subject=subject,
            message=text_body,
            html_message=html_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
    except Exception as exc:
        # Une panne SMTP ne doit pas faire échouer l'action de modération,
        # mais elle ne doit pas non plus passer inaperçue.
        logger.error("Notification de modération non envoyée à %s : %s", recipient, exc)
        return False

    return True
