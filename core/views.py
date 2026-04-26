import os
import uuid

from datetime import date, datetime, timedelta

from django.conf import settings
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db.models import Count, Q, F
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.text import slugify


from core.forms import AlertForm, MAX_ALERTS_PER_EMAIL, OfferForm, SignUpForm
from core.models import Alert, Offer, OfferPhoto
from core.tasks import moderate_offer
from promote.models import Promote


# Create your views here.
def _build_offer_queryset(get_params):
    search_query  = get_params.get('search', '').strip()
    section       = get_params.get('section', '')
    offer_type    = get_params.get('type', '')
    category      = get_params.get('category', '')
    gender_filter = get_params.get('gender', '')
    age_min       = get_params.get('age_min', '')
    age_max       = get_params.get('age_max', '')
    freshness     = get_params.get('freshness', '')

    qs = Offer.objects.filter(filled=False).filter(
        moderation_status=Offer.PUBLISHED
    )
    if search_query:
        qs = qs.filter(
            Q(title__icontains=search_query) |
            Q(summary__icontains=search_query) |
            Q(city__icontains=search_query)
        )
    if section:
        qs = qs.filter(section=section)
    if offer_type:
        qs = qs.filter(type=offer_type)
    if category:
        qs = qs.filter(category=category)

    # Genre — inclusif : si l'annonce ne précise pas de genre, elle remonte toujours
    if gender_filter:
        qs = qs.filter(
            Q(gender=gender_filter) | Q(gender__isnull=True) | Q(gender='')
        )

    # Âge — inclusif : les annonces sans tranche d'âge remontent toujours
    if age_min:
        try:
            qs = qs.filter(Q(max_age__isnull=True) | Q(max_age__gte=int(age_min)))
        except ValueError:
            pass
    if age_max:
        try:
            qs = qs.filter(Q(min_age__isnull=True) | Q(min_age__lte=int(age_max)))
        except ValueError:
            pass

    # Fraîcheur
    if freshness == 'week':
        qs = qs.filter(created_on__gte=datetime.now() - timedelta(weeks=1))
    elif freshness == 'month':
        qs = qs.filter(created_on__gte=datetime.now() - timedelta(days=30))

    return qs.order_by('-created_on')


def index(request):
    is_htmx = request.META.get('HTTP_HX_REQUEST') == 'true'
    page     = max(1, int(request.GET.get('page', 1)))

    qs          = _build_offer_queryset(request.GET)
    total       = qs.count()
    page_offers = qs[(page - 1) * 20: page * 20]
    has_more    = total > page * 20

    ctx = {
        'all_offers': page_offers,
        'has_more':   has_more,
        'page':       page,
        'page_next':  page + 1,
        'is_htmx':    is_htmx,
    }

    if is_htmx:
        return render(request, 'core/partials/offers_partials.html', ctx)

    today = date.today()
    promo = Promote.objects.filter(start_date__lte=today, end_date__gte=today).order_by('?').first()
    if promo:
        Promote.objects.filter(pk=promo.pk).update(impression_count=F("impression_count") + 1)
    else:
        promo = Promote.objects.filter(slug__exact='your-ad').first()

    ctx['promo'] = promo
    return render(request, 'core/index.html', ctx)


def offers(request, page: int):
    all_offers = Offer.objects.filter(filled=False).filter(
        moderation_status=Offer.PUBLISHED).order_by('-created_on')
    return render(request, 'core/partials/offers_partials.html', {
        'all_offers': all_offers[(page-1)*20:(page)*20],
        'page': page,
        'page_next': page+1,
    })

def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            form.save()
            email = form.cleaned_data.get('email')
            raw_password = form.cleaned_data.get('password1')
            user = authenticate(email=email, password=raw_password)
            login(request, user)
            next_url = request.POST.get('next') or request.GET.get('next') or 'index'
            return redirect(next_url)
    else:
        form = SignUpForm()
    return render(request, 'registration/signup.html', {
        'form': form,
        'next': request.GET.get('next', ''),
    })


def _save_extra_photos(offer, files):
    existing_count = offer.photos.count()
    for i, file in enumerate(files):
        photo = OfferPhoto(offer=offer, order=existing_count + i)
        photo.save()
        photo.image = file
        photo.save(update_fields=['image'])


def _delete_extra_photos(offer, post_data):
    for key in post_data:
        if key.startswith('delete_photo_'):
            pk = key.removeprefix('delete_photo_')
            offer.photos.filter(pk=pk).delete()


def add_offer(request):
    MAPBOX_ACCESS_TOKEN = os.environ.get("MAPBOX_ACCESS_TOKEN")
    # with open('blogApp/static/fr_cities.json') as f:
    #     fr_cities = json.load(f)
    if request.method == 'POST':
        form = OfferForm(request.POST, request.FILES)
        if form.is_valid():
            offer = form.save(commit=False)
            offer.author = request.user
            offer.moderation_status = Offer.UNDER_REVIEW
            offer.save()
            _save_extra_photos(offer, request.FILES.getlist('extra_photos'))
            moderate_offer.delay(offer.id)
            offer_id = offer.id
            return redirect('offer', offer_id=offer_id)
    else:
        form = OfferForm()
    return render(request,
                  'core/add_offer.html',
                  {'form': form, 'offer_id': -1, 'MAPBOX_ACCESS_TOKEN': MAPBOX_ACCESS_TOKEN})


@login_required
def update_offer(request, offer_id: int):
    MAPBOX_ACCESS_TOKEN = os.environ.get("MAPBOX_ACCESS_TOKEN")
    if request.method == 'POST':
        offer = get_object_or_404(Offer, id=offer_id)
        if offer.author != request.user:
            return redirect('offer', offer_id=offer_id)
        if offer.moderation_status == Offer.UNDER_REVIEW:
            from django.contrib import messages as django_messages
            django_messages.error(request, "Votre annonce est en cours d'examen et ne peut pas être modifiée pour le moment.")
            return redirect('offer', offer_id=offer_id)
        form = OfferForm(request.POST, request.FILES, instance=offer)
        if form.is_valid():
            offer = form.save(commit=False)
            offer.moderation_status = Offer.UNDER_REVIEW
            offer.save()
            _delete_extra_photos(offer, request.POST)
            _save_extra_photos(offer, request.FILES.getlist('extra_photos'))
            moderate_offer.delay(offer.id)
            return redirect('offer', offer_id=offer_id)
    else:
        offer = get_object_or_404(Offer, id=offer_id)
        if offer.author != request.user:
            return redirect('offer', offer_id=offer_id)
        if offer.moderation_status == Offer.UNDER_REVIEW:
            from django.contrib import messages as django_messages
            django_messages.error(request, "Votre annonce est en cours d'examen et ne peut pas être modifiée pour le moment.")
            return redirect('offer', offer_id=offer_id)
        form = OfferForm(instance=offer)
    return render(request,
                  'core/add_offer.html',
                  {'form': form, 'offer_id': offer_id, 'MAPBOX_ACCESS_TOKEN': MAPBOX_ACCESS_TOKEN})


@login_required
def delete_offer(request, offer_id: int):
    if request.user.id == Offer.objects.get(pk=offer_id).author.id:
        Offer.objects.get(pk=offer_id).delete()
        return redirect('index')
    else:
        return redirect('index')


@login_required
def fill_offer(request, offer_id: int):
    if request.user.id == Offer.objects.get(pk=offer_id).author.id:
        offer = get_object_or_404(Offer, pk=offer_id)
        offer.filled = True
        offer.save()
        return redirect('offer', offer_id=offer_id)
    else:
        return redirect('offer', offer_id=offer_id)


@login_required
def unfill_offer(request, offer_id: int):
    if request.user.id == Offer.objects.get(pk=offer_id).author.id:
        offer = get_object_or_404(Offer, pk=offer_id)
        offer.filled = False
        offer.save()
        return redirect('offer', offer_id=offer_id)
    else:
        return redirect('offer', offer_id=offer_id)



def offer(request, offer_id: int):
    offer = get_object_or_404(Offer, pk=offer_id)
    if offer.moderation and not offer.moderation.passed:
        return render(request, 'core/offer_moderation_failed.html', {'offer': offer})
    return render(request, 'core/offer.html', {'offer': offer})


def offer_search(request):
    search_data = request.POST

    # Champs du formulaire
    search_query = search_data.get('search', '').strip()
    section = search_data.get('section')
    offer_type = search_data.get('type')
    category = search_data.get('category')

    # Base queryset
    results = Offer.objects.filter(filled=False).filter(
        moderation_status=Offer.PUBLISHED
    )

    # Filtres dynamiques
    if search_query:
        results = results.filter(
            Q(title__icontains=search_query) |
            Q(summary__icontains=search_query) |
            Q(city__icontains=search_query)
        )

    if section:
        results = results.filter(section=section)

    if offer_type:
        results = results.filter(type=offer_type)

    if category:
        results = results.filter(category=category)

    context = {
        'all_offers': results.order_by('-created_on')
    }

    return render(request, 'core/partials/offers_partials.html', context)


@login_required
def offer_user(request):
    user_offers = Offer.objects.select_related('moderation').filter(author=request.user.id)
    context = {
        'all_offers': user_offers.order_by('-created_on')
    }
    return render(request, 'core/offer_user.html', context)



def offer_contact_info(request, offer_id: int):
    offer = get_object_or_404(Offer, pk=offer_id)
    return render(request, 'core/partials/offer_contact_info.html', {'offer': offer})


def about(request):
    return render(request, 'core/about.html')


def tou(request):
    return render(request, 'core/tou.html')

def announcement(request):
    return render(request, 'core/announcement.html')


def alert(request):
    """Création d'une alerte email."""
    authenticated = request.user.is_authenticated
    if request.method == 'POST':
        data = request.POST.copy()
        if authenticated:
            data['email'] = request.user.email
        form = AlertForm(data)
        if form.is_valid():
            alert_obj = form.save(commit=False)
            if authenticated:
                alert_obj.confirmed = True
            alert_obj.save()
            if authenticated:
                return redirect('alert_user')
            _send_alert_confirmation(alert_obj, request)
            return render(request, 'core/alert_pending.html', {'email': alert_obj.email})
    else:
        initial = {k: request.GET.get(k, '') for k in
                   ('search', 'section', 'offer_type', 'category', 'gender', 'age_min', 'age_max')}
        initial['offer_type'] = request.GET.get('type', '')
        if authenticated:
            initial['email'] = request.user.email
        form = AlertForm(initial=initial)
    return render(request, 'core/alert.html', {
        'form': form,
        'max_alerts': MAX_ALERTS_PER_EMAIL,
        'authenticated': authenticated,
    })


def alert_confirm(request, token):
    """Confirmation de l'alerte via le lien email."""
    alert_obj = get_object_or_404(Alert, token=token)
    if not alert_obj.confirmed:
        alert_obj.confirmed = True
        alert_obj.save(update_fields=['confirmed'])
    return render(request, 'core/alert_confirmed.html', {'alert': alert_obj})


def alert_unsubscribe(request, token):
    """Désactivation d'une alerte (lien dans les emails de notification)."""
    alert_obj = get_object_or_404(Alert, token=token)
    alert_obj.active = False
    alert_obj.save(update_fields=['active'])
    return render(request, 'core/alert_unsubscribed.html', {'alert': alert_obj})


@login_required
def alert_user(request):
    """Mes alertes — accès via compte connecté."""
    if request.method == 'POST':
        delete_token = request.POST.get('delete_token')
        if delete_token:
            Alert.objects.filter(email=request.user.email, token=delete_token).delete()
        return redirect('alert_user')
    alerts = Alert.objects.filter(email=request.user.email, confirmed=True).order_by('-created_at')
    return render(request, 'core/alert_manage.html', {'alerts': alerts, 'pivot_token': None})


def alert_manage(request, token):
    """Page de gestion de toutes les alertes associées à cet email."""
    alert_obj = get_object_or_404(Alert, token=token, confirmed=True)
    if request.method == 'POST':
        delete_token = request.POST.get('delete_token')
        if delete_token:
            Alert.objects.filter(email=alert_obj.email, token=delete_token).delete()
        return redirect('alert_manage', token=token)
    alerts = Alert.objects.filter(email=alert_obj.email, confirmed=True).order_by('-created_at')
    return render(request, 'core/alert_manage.html', {'alerts': alerts, 'pivot_token': token})


def _send_alert_confirmation(alert_obj, request):
    confirm_url = request.build_absolute_uri(
        reverse('alert_confirm', kwargs={'token': alert_obj.token})
    )
    subject = "Confirmez votre alerte — Petites Annonces Théâtre"
    html_body = render_to_string('emails/alert_confirmation.html', {
        'alert': alert_obj,
        'confirm_url': confirm_url,
    })
    text_body = (
        f"Confirmez votre alerte en cliquant sur ce lien :\n{confirm_url}\n\n"
        f"Critères : {alert_obj.filter_summary()}\n"
        f"Fréquence : {alert_obj.get_frequency_display()}"
    )
    send_mail(subject, text_body, settings.DEFAULT_FROM_EMAIL,
              [alert_obj.email], html_message=html_body, fail_silently=True)


# ── Helpers villes ────────────────────────────────────────────────────────────

def _moderation_filter():
    return Q(moderation__isnull=True) | Q(moderation__passed=True)


def _find_city_by_slug(city_slug):
    """Retourne le nom exact de la ville correspondant au slug URL, ou None."""
    cities = (
        Offer.objects
        .exclude(city='')
        .values_list('city', flat=True)
        .distinct()
    )
    for city in cities:
        if slugify(city) == city_slug:
            return city
    return None


def _get_active_cities(min_count=3, limit=None):
    """Villes avec au moins min_count annonces actives dans les 6 derniers mois."""
    six_months_ago = datetime.now() - timedelta(days=180)
    qs = (
        Offer.objects
        .filter(filled=False, created_on__gte=six_months_ago)
        .exclude(city='')
        .filter(_moderation_filter())
        .values('city')
        .annotate(count=Count('id'))
        .filter(count__gte=min_count)
        .order_by('-count')
    )
    if limit:
        qs = qs[:limit]
    return [(c['city'], slugify(c['city']), c['count']) for c in qs]


# ── Vues villes ────────────────────────────────────────────────────────────────

def city_offers(request, city_slug):
    city = _find_city_by_slug(city_slug)
    if city is None:
        raise Http404

    is_htmx = request.META.get('HTTP_HX_REQUEST') == 'true'
    page = max(1, int(request.GET.get('page', 1)))

    qs = (
        Offer.objects
        .select_related('moderation')
        .filter(city__iexact=city, filled=False)
        .filter(_moderation_filter())
        .order_by('-created_on')
    )
    total = qs.count()
    page_offers = qs[(page - 1) * 20: page * 20]
    has_more = total > page * 20
    pagination_url = reverse('city_offers', kwargs={'city_slug': city_slug})

    ctx = {
        'all_offers': page_offers,
        'has_more': has_more,
        'page': page,
        'page_next': page + 1,
        'city': city,
        'city_slug': city_slug,
        'is_htmx': is_htmx,
        'pagination_url': pagination_url,
    }

    if is_htmx:
        return render(request, 'core/partials/offers_partials.html', ctx)

    if total == 0:
        three_months_ago = datetime.now() - timedelta(days=90)
        ctx['recent_filled'] = (
            Offer.objects
            .filter(city__iexact=city)
            .filter(_moderation_filter())
            .filter(created_on__gte=three_months_ago)
            .order_by('-created_on')[:10]
        )

    return render(request, 'core/city_offers.html', ctx)


def city_list(request):
    cities = _get_active_cities(min_count=3)
    return render(request, 'core/city_list.html', {'cities': cities})


# ── Helpers départements ──────────────────────────────────────────────────────

def _extract_department(city_str):
    """Extrait le département du champ city (format Mapbox : 'Ville, Département, France')."""
    if not city_str:
        return ''
    parts = [p.strip() for p in city_str.split(',')]
    if len(parts) >= 3:
        candidate = parts[-2]
        if candidate.lower() not in ('france', 'belgique', 'suisse', 'luxembourg', 'canada'):
            return candidate
    return ''


def _find_department_by_slug(dept_slug):
    cities = (
        Offer.objects
        .exclude(city='')
        .values_list('city', flat=True)
        .distinct()
    )
    seen = set()
    for city in cities:
        dept = _extract_department(city)
        if dept and dept not in seen:
            seen.add(dept)
            if slugify(dept) == dept_slug:
                return dept
    return None


def _get_active_departments(min_count=3, limit=None):
    six_months_ago = datetime.now() - timedelta(days=180)
    cities = (
        Offer.objects
        .filter(filled=False, created_on__gte=six_months_ago)
        .exclude(city='')
        .filter(_moderation_filter())
        .values_list('city', flat=True)
    )
    dept_counts = {}
    for city in cities:
        dept = _extract_department(city)
        if dept:
            dept_counts[dept] = dept_counts.get(dept, 0) + 1

    result = [
        (dept, slugify(dept), count)
        for dept, count in dept_counts.items()
        if count >= min_count
    ]
    result.sort(key=lambda x: -x[2])
    if limit:
        result = result[:limit]
    return result


# ── Vues départements ─────────────────────────────────────────────────────────

def department_offers(request, dept_slug):
    department = _find_department_by_slug(dept_slug)
    if department is None:
        raise Http404

    is_htmx = request.META.get('HTTP_HX_REQUEST') == 'true'
    page = max(1, int(request.GET.get('page', 1)))

    qs = (
        Offer.objects
        .select_related('moderation')
        .filter(city__icontains=', ' + department, filled=False)
        .filter(_moderation_filter())
        .order_by('-created_on')
    )
    total = qs.count()
    page_offers = qs[(page - 1) * 20: page * 20]
    has_more = total > page * 20
    pagination_url = reverse('department_offers', kwargs={'dept_slug': dept_slug})

    ctx = {
        'all_offers': page_offers,
        'has_more': has_more,
        'page': page,
        'page_next': page + 1,
        'department': department,
        'dept_slug': dept_slug,
        'is_htmx': is_htmx,
        'pagination_url': pagination_url,
    }

    if is_htmx:
        return render(request, 'core/partials/offers_partials.html', ctx)

    if total == 0:
        three_months_ago = datetime.now() - timedelta(days=90)
        ctx['recent_filled'] = (
            Offer.objects
            .filter(city__icontains=', ' + department)
            .filter(_moderation_filter())
            .filter(created_on__gte=three_months_ago)
            .order_by('-created_on')[:10]
        )

    return render(request, 'core/department_offers.html', ctx)


def department_list(request):
    departments = _get_active_departments(min_count=3)
    return render(request, 'core/department_list.html', {'departments': departments})
