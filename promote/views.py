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
        click_count = F("click_count") + 1
    )

    # redirige vers la page détail
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


def sponsor_checkout(request, play_id):
    return HttpResponse("Not implemented", status=501)


def stripe_webhook(request):
    return HttpResponse("Not implemented", status=501)


def sponsor_confirmation(request, session_id):
    return HttpResponse("Not implemented", status=501)


def sponsor_cancel(request):
    return HttpResponse("Not implemented", status=501)