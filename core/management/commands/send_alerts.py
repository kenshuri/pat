from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

from core.models import Alert
from core.views import _build_offer_queryset


class Command(BaseCommand):
    help = "Envoie les alertes email selon la fréquence demandée."

    def add_arguments(self, parser):
        parser.add_argument(
            '--frequency',
            choices=[Alert.IMMEDIATE, Alert.DAILY, Alert.WEEKLY],
            required=True,
        )

    def handle(self, *args, **options):
        frequency = options['frequency']
        now = timezone.now()
        site_url = getattr(settings, 'SITE_URL', 'https://petites-annonces-theatre.fr')

        alerts = Alert.objects.filter(confirmed=True, active=True, frequency=frequency)
        sent = skipped = 0

        for alert in alerts:
            since = alert.last_sent_at or alert.created_at

            params = {
                'search':   alert.search,
                'section':  alert.section,
                'type':     alert.offer_type,
                'category': alert.category,
                'gender':   alert.gender,
                'age_min':  str(alert.age_min) if alert.age_min else '',
                'age_max':  str(alert.age_max) if alert.age_max else '',
            }
            new_offers = list(
                _build_offer_queryset(params)
                .filter(created_on__gt=since)
                .order_by('-created_on')[:10]
            )

            if not new_offers:
                skipped += 1
                continue

            count = len(new_offers)
            subject = (
                f"{count} nouvelle{'s' if count > 1 else ''} annonce{'s' if count > 1 else ''} "
                f"— Petites Annonces Théâtre"
            )
            ctx = {'alert': alert, 'offers': new_offers, 'site_url': site_url}
            html_body = render_to_string('emails/alert_notification.html', ctx)
            text_body = "\n\n".join(
                f"{o.title} — {o.city}\n{o.summary}\n{site_url}/offer/{o.pk}"
                for o in new_offers
            )
            send_mail(
                subject, text_body,
                settings.DEFAULT_FROM_EMAIL,
                [alert.email],
                html_message=html_body,
                fail_silently=False,
            )
            alert.last_sent_at = now
            alert.save(update_fields=['last_sent_at'])
            sent += 1

        self.stdout.write(
            self.style.SUCCESS(f"[send_alerts] {frequency}: {sent} envoyé(s), {skipped} sans nouveauté")
        )
