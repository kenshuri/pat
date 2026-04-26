import logging
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def ping():
    logger.info("Celery ping task executed.")
    return "pong"


@shared_task
def moderate_offer(offer_id: int):
    from core.models import Offer
    from core.services.image_moderation import moderate_images
    from moderation.services import moderate_text

    try:
        offer = Offer.objects.select_related('moderation', 'author').prefetch_related('photos').get(pk=offer_id)
    except Offer.DoesNotExist:
        logger.warning("moderate_offer: Offer %s not found", offer_id)
        return

    try:
        # 1. Modération texte
        text_result = moderate_text(offer.get_moderation_text())

        # 2. Modération images
        images_ok, image_reasons = moderate_images(offer)

        # 3. Mise à jour ModerationResult
        text_result.images_passed = images_ok
        text_result.image_reasons = image_reasons
        text_result.save()

        offer.moderation = text_result

        # 4. Décision finale
        if text_result.passed and images_ok:
            offer.moderation_status = Offer.PUBLISHED
        else:
            offer.moderation_status = Offer.UNDER_REVIEW
            _notify_admin_flagged(offer, text_result)

        offer.save(update_fields=['moderation', 'moderation_status'])

    except Exception as e:
        logger.error("moderate_offer failed for offer %s: %s", offer_id, e)
        # fail closed: moderation_status stays under_review


def _notify_admin_flagged(offer, moderation_result):
    reasons = []
    if not moderation_result.passed and moderation_result.reasons:
        reasons.append(f"Texte : {moderation_result.reasons}")
    if not moderation_result.images_passed and moderation_result.image_reasons:
        reasons.append(f"Images : {moderation_result.image_reasons}")

    admin_emails = [email for _, email in settings.ADMINS]
    if not admin_emails:
        return

    subject = f"[PAT] Annonce #{offer.pk} flagguée — {offer.title}"
    site_url = getattr(settings, 'SITE_URL', 'https://petites-annonces-theatre.fr')
    body = render_to_string('emails/moderation_flagged.html', {
        'offer': offer,
        'reasons': reasons,
        'admin_url': f"{site_url}/admin/core/offer/{offer.pk}/change/",
        'author_email': getattr(offer.author, 'email', '—') if offer.author else '—',
    })

    send_mail(
        subject=subject,
        message="\n".join(reasons),
        html_message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=admin_emails,
        fail_silently=True,
    )
