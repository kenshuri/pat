import json
import logging
from datetime import date, timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.http import HttpResponseBadRequest, JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import DetailView
from django.template.loader import select_template

import stripe

from promote.models import Promote

logger = logging.getLogger(__name__)


# Create your views here.
def default(request):
    return render(request, 'promote/default.html')


def banner_click(request, slug):
    promo = get_object_or_404(Promote, slug=slug)

    Promote.objects.filter(pk=promo.pk).update(
        click_count=F("click_count") + 1
    )

    if promo.play_id:
        return redirect("shows:play_detail", pk=promo.play_id)
    return redirect("promote:detail", slug=slug)

class PromoteDetailView(DetailView):
    model = Promote
    context_object_name = "promo"
    slug_field = "slug"      # (default, but explicit)
    slug_url_kwarg = "slug"  # (default, but explicit)

    # ↓ dynamic template resolution
    def get_template_names(self):
        """
        1. Try  promote/<slug>.html          (e.g. promote/romeo-et-juliette.html)
        2. Fallback to promote/promote.html  (generic template)
        """
        slug = self.kwargs.get(self.slug_url_kwarg)
        candidates = [
            f"promote/details_{slug}.html",
            "promote/details_your-ad.html",
        ]
        # select_template returns the first template that actually exists
        return [select_template(candidates).template.name]

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)

        # obj existe maintenant
        Promote.objects.filter(pk=self.object.pk).update(
            detail_view_count=F("detail_view_count") + 1
        )
        return response


def booking_redirect(request, slug):
    promo = get_object_or_404(Promote, slug=slug)

    # 1) compteur atomique
    Promote.objects.filter(pk=promo.pk).update(
        booking_click_count=F("booking_click_count") + 1
    )

    # 2) URL externe passée dans ?next=
    target = request.GET.get("next")
    if not target:
        return redirect("promote:detail", slug=slug)

    # (optionnel) sécurise un peu : refuse javascript: etc.
    if urlparse(target).scheme not in ("http", "https"):
        return HttpResponseBadRequest("URL non valide.")

    return redirect(target)


FORMULA_DAYS   = {'day': 0,  'week': 6,  'month': 29}
FORMULA_PRICES = {'day': 300, 'week': 1000, 'month': 3000}
FORMULA_LABELS = {'day': 'Jour', 'week': 'Semaine', 'month': 'Mois'}


@login_required
def sponsor_list(request):
    play_id = request.GET.get('play')
    if play_id:
        return redirect(f"{reverse('promote:sponsor_calendar')}?play={play_id}")
    from shows.models import Play
    plays = Play.objects.filter(user=request.user, moderation_status='published')
    return render(request, 'promote/sponsor_list.html', {'plays': plays})


@login_required
def sponsor_calendar(request):
    from shows.models import Play
    play_id = request.GET.get('play')
    selected_play = None
    if play_id:
        selected_play = get_object_or_404(
            Play, pk=play_id, user=request.user, moderation_status='published'
        )
    plays = Play.objects.filter(user=request.user, moderation_status='published')
    formula_options = [
        ('day',   'Jour',    3),
        ('week',  'Semaine', 10),
        ('month', 'Mois',    30),
    ]
    return render(request, 'promote/sponsor_calendar.html', {
        'plays': plays,
        'selected_play': selected_play,
        'formula_options': formula_options,
    })


@login_required
def sponsor_availability(request):
    today = date.today()
    booked = Promote.objects.filter(
        status='confirmed',
        end_date__gte=today,
    ).values('start_date', 'end_date')
    return JsonResponse({
        'booked': [
            {'start': str(p['start_date']), 'end': str(p['end_date'])}
            for p in booked
        ]
    })


@login_required
def sponsor_checkout(request, play_id):
    from shows.models import Play
    from datetime import date as date_type

    play = get_object_or_404(
        Play, pk=play_id, user=request.user, moderation_status='published'
    )

    if request.method != 'POST':
        return redirect(f"{reverse('promote:sponsor_calendar')}?play={play_id}")

    formula = request.POST.get('formula', '')
    start_date_str = request.POST.get('start_date', '')

    if formula not in FORMULA_DAYS:
        messages.error(request, "Formule invalide.")
        return redirect(f"{reverse('promote:sponsor_calendar')}?play={play_id}")

    try:
        start_date = date_type.fromisoformat(start_date_str)
    except (ValueError, TypeError):
        messages.error(request, "Date de début invalide.")
        return redirect(f"{reverse('promote:sponsor_calendar')}?play={play_id}")

    end_date = start_date + timedelta(days=FORMULA_DAYS[formula])

    overlap = Promote.objects.filter(
        status='confirmed',
        start_date__lte=end_date,
        end_date__gte=start_date,
    ).exists()

    if overlap:
        messages.error(request, "Cette période est déjà réservée. Choisissez une autre date.")
        return redirect(f"{reverse('promote:sponsor_calendar')}?play={play_id}")

    promote = Promote.objects.create(
        user=request.user,
        play=play,
        title=play.title,
        start_date=start_date,
        end_date=end_date,
        formula=formula,
        status='pending_payment',
    )

    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'eur',
                    'unit_amount': FORMULA_PRICES[formula],
                    'product_data': {
                        'name': f"Bandeau — {play.title} ({FORMULA_LABELS[formula]})",
                        'description': (
                            f"{start_date.strftime('%d/%m/%Y')} – {end_date.strftime('%d/%m/%Y')}"
                            f" · {request.user.email}"
                        ),
                    },
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=(
                request.build_absolute_uri('/').rstrip('/')
                + '/promote/sponsor/confirmation/{CHECKOUT_SESSION_ID}/'
            ),
            cancel_url=request.build_absolute_uri(reverse('promote:sponsor_cancel')),
            metadata={'promote_id': str(promote.pk)},
            customer_email=request.user.email,
        )
    except Exception as e:
        logger.error("Stripe session creation failed for promote %s: %s", promote.pk, e)
        promote.delete()
        messages.error(request, "Une erreur est survenue lors du paiement. Veuillez réessayer.")
        return redirect(f"{reverse('promote:sponsor_calendar')}?play={play_id}")

    promote.stripe_session_id = session.id
    promote.save(update_fields=['stripe_session_id'])

    return redirect(session.url)


def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError as e:
        logger.error("Stripe webhook signature error: %s", e)
        return HttpResponse(status=200)

    if event.type == 'checkout.session.completed':
        session = event.data.object
        metadata = getattr(session, 'metadata', None)
        promote_id = getattr(metadata, 'promote_id', None) if metadata else None

        if promote_id:
            try:
                promote = Promote.objects.get(pk=promote_id)

                overlap = Promote.objects.filter(
                    status='confirmed',
                    start_date__lte=promote.end_date,
                    end_date__gte=promote.start_date,
                ).exclude(pk=promote.pk).exists()

                if overlap:
                    logger.warning(
                        "Promote %s: overlapping confirmed slot, skipping confirm", promote_id
                    )
                else:
                    promote.status = 'confirmed'
                    promote.price_paid = (getattr(session, 'amount_total', 0) or 0) / 100
                    promote.save(update_fields=['status', 'price_paid'])

            except Promote.DoesNotExist:
                logger.error("Webhook: Promote %s not found", promote_id)

    return HttpResponse(status=200)


@login_required
def sponsor_confirmation(request, session_id):
    promote = get_object_or_404(
        Promote, stripe_session_id=session_id, user=request.user
    )

    # If webhook hasn't fired yet, confirm directly via Stripe API
    if promote.status == 'pending_payment':
        try:
            stripe.api_key = settings.STRIPE_SECRET_KEY
            session = stripe.checkout.Session.retrieve(session_id)
            if getattr(session, 'payment_status', None) == 'paid':
                overlap = Promote.objects.filter(
                    status='confirmed',
                    start_date__lte=promote.end_date,
                    end_date__gte=promote.start_date,
                ).exclude(pk=promote.pk).exists()
                if not overlap:
                    amount = getattr(session, 'amount_total', 0) or 0
                    promote.status = 'confirmed'
                    promote.price_paid = amount / 100
                    promote.save(update_fields=['status', 'price_paid'])
        except Exception as e:
            logger.warning("Could not verify Stripe session %s: %s", session_id, e)

    today = date.today()
    is_active = promote.start_date <= today <= promote.end_date
    return render(request, 'promote/sponsor_confirmation.html', {
        'promote': promote,
        'is_active': is_active,
    })


@login_required
def sponsor_cancel(request):
    return render(request, 'promote/sponsor_cancel.html')


def sponsor_landing(request):
    return render(request, 'promote/sponsor_landing.html')


@login_required
def my_promotions(request):
    today = date.today()
    promotions = Promote.objects.filter(
        user=request.user
    ).order_by('-start_date')
    for p in promotions:
        if p.status == 'pending_payment':
            p.display_status = 'pending_payment'
        elif p.end_date < today:
            p.display_status = 'expired'
        elif p.start_date > today:
            p.display_status = 'upcoming'
        else:
            p.display_status = 'active'
    return render(request, 'promote/my_promotions.html', {'promotions': promotions})