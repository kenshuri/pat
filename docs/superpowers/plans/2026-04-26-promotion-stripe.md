# Promotion Stripe — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow logged-in users to pay via Stripe to display their published play in the homepage promotional banner for a reserved time slot.

**Architecture:** Extend the existing `Promote` model with Stripe/play fields; add self-service sponsor views under `/promote/sponsor/`; webhook confirms payment and sets `status='confirmed'`; `core/views.index` prioritises play-based promos, falls back to legacy slug-based banners. Existing manually-created banners kept working via a data migration that sets their status to `confirmed`.

**Tech Stack:** Django 5.1, stripe-python, Flatpickr (CDN), SQLite (tests), `uv run python manage.py test`

---

## Structure des fichiers

| Fichier | Action |
|---------|--------|
| `pyproject.toml` | Ajouter `stripe` |
| `config/settings.py` | Ajouter `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` |
| `promote/models.py` | Ajouter `play`, `stripe_session_id`, `formula`, `status` ; mettre à jour `save()` |
| `promote/migrations/0002_add_stripe_fields.py` | Migration + data migration pour promos existantes |
| `promote/views.py` | Ajouter 7 vues sponsor + webhook |
| `promote/urls.py` | Ajouter 7 URLs sponsor |
| `promote/tests.py` | Créer — tous les tests promote |
| `promote/templates/promote/sponsor_list.html` | Liste des pièces publiées de l'utilisateur |
| `promote/templates/promote/sponsor_calendar.html` | Calendrier Flatpickr + formulaire |
| `promote/templates/promote/sponsor_confirmation.html` | Page post-paiement |
| `promote/templates/promote/sponsor_cancel.html` | Page annulation Stripe |
| `promote/templates/promote/banner_play.html` | Bandeau générique pièce |
| `promote/admin.py` | Ajouter `play`, `status`, `formula` + action `marquer_expire` |
| `core/views.py` | Mettre à jour la logique de sélection du bandeau (lignes 98–105) |
| `core/templates/core/index.html` | Inclusion conditionnelle `banner_play.html` vs slug (lignes 57–60) |
| `shows/templates/shows/partials/play_owner_zone.html` | Ajouter bouton « Promouvoir cette pièce » |

---

## Task 1 : Dépendance stripe + variables settings

**Files:**
- Modify: `pyproject.toml`
- Modify: `config/settings.py`

- [ ] **Step 1 : Ajouter stripe à pyproject.toml**

Dans la section `dependencies`, ajouter après `"requests>=2.32.5,"` :

```toml
    "stripe>=11.0",
```

- [ ] **Step 2 : Installer**

```bash
uv sync
```

Expected: `stripe` appears in `.venv`.

- [ ] **Step 3 : Ajouter les variables Stripe dans config/settings.py**

Chercher la ligne `SITE_URL = 'https://petites-annonces-theatre.fr'` (ligne ~39) et ajouter juste après :

```python
STRIPE_SECRET_KEY      = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
STRIPE_WEBHOOK_SECRET  = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
```

- [ ] **Step 4 : Vérifier**

```bash
uv run python manage.py check
```

Expected: System check identified no issues.

- [ ] **Step 5 : Commit**

```bash
git add pyproject.toml uv.lock config/settings.py
git commit -m "feat: add stripe dependency and settings"
```

---

## Task 2 : Étendre le modèle Promote + migration

**Files:**
- Modify: `promote/models.py`
- Create: `promote/migrations/0002_add_stripe_fields.py` (via makemigrations)
- Create: `promote/tests.py`

- [ ] **Step 1 : Écrire les tests**

Créer `promote/tests.py` :

```python
from datetime import date, timedelta
from django.test import TestCase
from accounts.models import CustomUser
from shows.models import Play
from promote.models import Promote


class PromoteModelTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email='promo@example.com', password='password123'
        )
        self.play = Play.objects.create(
            user=self.user, title='Roméo et Juliette',
            genre='theatre', moderation_status='published',
        )

    def test_default_status_is_pending_payment(self):
        promo = Promote(
            user=self.user,
            title='Test',
            start_date=date.today(),
            end_date=date.today() + timedelta(days=6),
        )
        self.assertEqual(promo.status, 'pending_payment')

    def test_slug_generated_from_play_and_date(self):
        start = date(2026, 5, 10)
        promo = Promote.objects.create(
            user=self.user,
            play=self.play,
            title=self.play.title,
            start_date=start,
            end_date=start + timedelta(days=6),
            formula='week',
        )
        self.assertEqual(promo.slug, 'romeo-et-juliette-2026-05-10')

    def test_slug_generated_from_title_when_no_play(self):
        promo = Promote.objects.create(
            user=self.user,
            title='Mon spectacle',
            start_date=date.today(),
            end_date=date.today(),
        )
        self.assertIn('mon-spectacle', promo.slug)

    def test_slug_collision_appends_counter(self):
        start = date(2026, 6, 1)
        Promote.objects.create(
            user=self.user, play=self.play, title=self.play.title,
            start_date=start, end_date=start, formula='day',
        )
        promo2 = Promote.objects.create(
            user=self.user, play=self.play, title=self.play.title,
            start_date=start, end_date=start, formula='day',
        )
        self.assertNotEqual(promo2.slug, 'romeo-et-juliette-2026-06-01')
        self.assertTrue(promo2.slug.startswith('romeo-et-juliette'))
```

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

```bash
uv run python manage.py test promote.tests.PromoteModelTests
```

Expected: FAIL — `Promote` n'a pas encore `play`, `formula`, `status`.

- [ ] **Step 3 : Mettre à jour promote/models.py**

Remplacer le contenu complet par :

```python
from datetime import timedelta
from django.db import models
from django.utils.text import slugify

from accounts.models import CustomUser


class Promote(models.Model):
    FORMULA_CHOICES = [
        ('day',   'Jour'),
        ('week',  'Semaine'),
        ('month', 'Mois'),
    ]
    STATUS_CHOICES = [
        ('pending_payment', 'En attente de paiement'),
        ('confirmed',       'Confirmé'),
        ('expired',         'Expiré'),
    ]

    # --- infos générales ----------------------------------------------------
    user   = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    title  = models.CharField(max_length=120)
    slug   = models.SlugField(unique=True, blank=True)

    # --- pièce associée (self-service) --------------------------------------
    play             = models.ForeignKey(
        'shows.Play', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='promotions',
    )
    stripe_session_id = models.CharField(max_length=255, blank=True, default='')
    formula           = models.CharField(
        max_length=10, choices=FORMULA_CHOICES, blank=True, default='',
    )
    status            = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending_payment',
    )

    # --- période de diffusion ----------------------------------------------
    start_date = models.DateField()
    end_date   = models.DateField()

    # --- statistiques -------------------------------------------------------
    impression_count    = models.PositiveIntegerField(default=0, editable=False)
    click_count         = models.PositiveIntegerField(default=0, editable=False)
    detail_view_count   = models.PositiveIntegerField(default=0, editable=False)
    booking_click_count = models.PositiveIntegerField(default=0, editable=False)

    # --- facturation --------------------------------------------------------
    price_paid = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Bandeau promotionnel'
        verbose_name_plural = 'Bandeaux promotionnels'

    def __str__(self):
        return f"{self.title} ({self.user})"

    @property
    def duration_days(self):
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return None

    def save(self, *args, **kwargs):
        if not self.slug:
            if self.play and self.start_date:
                base = f"{self.play.title}-{self.start_date}"
            else:
                base = self.title
            candidate = slugify(base)[:50]
            slug = candidate
            counter = 1
            while Promote.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{candidate[:47]}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)
```

- [ ] **Step 4 : Créer la migration**

```bash
uv run python manage.py makemigrations promote --name add_stripe_fields
```

- [ ] **Step 5 : Ajouter la data migration pour les promos existantes**

Ouvrir `promote/migrations/0002_add_stripe_fields.py` et ajouter une opération `RunPython` à la fin du bloc `operations` pour passer les promos manuelles (sans `play`) à `status='confirmed'` :

```python
from django.db import migrations, models
import django.db.models.deletion


def set_existing_confirmed(apps, schema_editor):
    Promote = apps.get_model('promote', 'Promote')
    Promote.objects.filter(play__isnull=True).update(status='confirmed')


class Migration(migrations.Migration):

    dependencies = [
        ('promote', '0001_initial'),
        ('shows', '0008_add_play_moderation'),
    ]

    operations = [
        # … opérations générées automatiquement …
        migrations.RunPython(set_existing_confirmed, migrations.RunPython.noop),
    ]
```

**Note :** Les opérations `AddField` générées automatiquement par makemigrations doivent rester présentes. Ajouter uniquement `RunPython` à la fin de la liste `operations` existante.

- [ ] **Step 6 : Appliquer la migration**

```bash
uv run python manage.py migrate
```

Expected: `Applying promote.0002_add_stripe_fields... OK`

- [ ] **Step 7 : Vérifier que les tests passent**

```bash
uv run python manage.py test promote.tests.PromoteModelTests
```

Expected: OK (4 tests)

- [ ] **Step 8 : Commit**

```bash
git add promote/models.py promote/migrations/ promote/tests.py
git commit -m "feat: extend Promote model with play, stripe_session_id, formula, status"
```

---

## Task 3 : URLs + vues liste / calendrier / disponibilités + templates

**Files:**
- Modify: `promote/urls.py`
- Modify: `promote/views.py`
- Create: `promote/templates/promote/sponsor_list.html`
- Create: `promote/templates/promote/sponsor_calendar.html`
- Modify: `promote/tests.py`

- [ ] **Step 1 : Écrire les tests**

Ajouter dans `promote/tests.py` :

```python
import json
from django.test import TestCase, Client
from django.urls import reverse


class SponsorListViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            email='list@example.com', password='password123'
        )
        self.play = Play.objects.create(
            user=self.user, title='Ma Pièce',
            genre='theatre', moderation_status='published',
        )

    def test_redirects_anonymous(self):
        response = self.client.get(reverse('promote:sponsor_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])

    def test_shows_published_plays(self):
        self.client.login(email='list@example.com', password='password123')
        response = self.client.get(reverse('promote:sponsor_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ma Pièce')

    def test_redirects_to_calendar_with_play_param(self):
        self.client.login(email='list@example.com', password='password123')
        response = self.client.get(
            reverse('promote:sponsor_list'), {'play': self.play.pk}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('calendar', response['Location'])


class AvailabilityViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            email='avail@example.com', password='password123'
        )

    def test_returns_json(self):
        self.client.login(email='avail@example.com', password='password123')
        response = self.client.get(reverse('promote:sponsor_availability'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        data = json.loads(response.content)
        self.assertIn('booked', data)

    def test_includes_confirmed_promos(self):
        play = Play.objects.create(
            user=self.user, title='Test Play',
            genre='theatre', moderation_status='published',
        )
        Promote.objects.create(
            user=self.user, play=play, title=play.title,
            start_date=date(2026, 7, 1), end_date=date(2026, 7, 7),
            formula='week', status='confirmed',
        )
        self.client.login(email='avail@example.com', password='password123')
        response = self.client.get(reverse('promote:sponsor_availability'))
        data = json.loads(response.content)
        slugs = [(b['start'], b['end']) for b in data['booked']]
        self.assertIn(('2026-07-01', '2026-07-07'), slugs)
```

- [ ] **Step 2 : Lancer pour vérifier l'échec**

```bash
uv run python manage.py test promote.tests.SponsorListViewTests promote.tests.AvailabilityViewTests
```

Expected: FAIL — URLs et vues n'existent pas encore.

- [ ] **Step 3 : Ajouter les URLs dans promote/urls.py**

Remplacer le contenu complet :

```python
from django.urls import path
from django.views.decorators.csrf import csrf_exempt

import promote.views
from . import views

app_name = "promote"

urlpatterns = [
    # --- legacy slug-based banner ---
    path("promote/<slug:slug>/", views.PromoteDetailView.as_view(), name="detail"),
    path("promote/<slug:slug>/click/", views.banner_click, name="banner_click"),
    path("promote/<slug:slug>/book/", views.booking_redirect, name="booking_redirect"),
    path("promote/", promote.views.default, name="default"),

    # --- self-service sponsor ---
    path("promote/sponsor/", views.sponsor_list, name="sponsor_list"),
    path("promote/sponsor/calendar/", views.sponsor_calendar, name="sponsor_calendar"),
    path("promote/sponsor/availability/", views.sponsor_availability, name="sponsor_availability"),
    path("promote/sponsor/checkout/<int:play_id>/", views.sponsor_checkout, name="sponsor_checkout"),
    path("promote/sponsor/confirmation/<str:session_id>/", views.sponsor_confirmation, name="sponsor_confirmation"),
    path("promote/sponsor/cancel/", views.sponsor_cancel, name="sponsor_cancel"),
    path("promote/sponsor/webhook/", csrf_exempt(views.stripe_webhook), name="stripe_webhook"),
]
```

- [ ] **Step 4 : Ajouter les vues dans promote/views.py**

Ajouter en haut du fichier les imports manquants :

```python
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

from promote.models import Promote

logger = logging.getLogger(__name__)
```

Puis ajouter ces vues à la fin du fichier :

```python
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
    return render(request, 'promote/sponsor_calendar.html', {
        'plays': plays,
        'selected_play': selected_play,
        'formula_prices': FORMULA_PRICES,
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
```

- [ ] **Step 5 : Créer promote/templates/promote/sponsor_list.html**

```html
{% extends "core/base.html" %}

{% block title %}Promouvoir ma pièce — Petites Annonces Théâtre{% endblock %}

{% block main %}
<div class="max-w-2xl mx-auto px-4 py-10">
    <h1 class="font-display font-bold text-ink text-xl uppercase tracking-[0.06em] mb-2">
        Promouvoir une pièce
    </h1>
    <p class="text-ink-soft text-sm mb-8">
        Choisissez la pièce que vous souhaitez mettre en avant dans le bandeau de la page d'accueil.
    </p>

    {% if plays %}
    <div class="space-y-3">
        {% for play in plays %}
        <a href="{% url 'promote:sponsor_calendar' %}?play={{ play.pk }}"
           class="flex items-center gap-4 p-4 border border-ink/10 hover:border-ink/30 transition-colors group">
            {% if play.poster %}
            <img src="{{ play.poster.url }}" alt="{{ play.title }}"
                 class="w-12 h-16 object-cover shrink-0">
            {% else %}
            <div class="w-12 h-16 bg-ink/5 shrink-0 flex items-center justify-center">
                <i class="fa-solid fa-masks-theater text-ink/20"></i>
            </div>
            {% endif %}
            <div class="min-w-0">
                <p class="font-display font-bold text-ink text-sm uppercase tracking-wide truncate
                          group-hover:text-primary transition-colors">
                    {{ play.title }}
                </p>
                {% if play.company %}
                <p class="text-ink-soft text-xs mt-0.5">{{ play.company }}</p>
                {% endif %}
            </div>
            <i class="fa-solid fa-chevron-right text-ink/20 group-hover:text-ink/50 transition-colors ml-auto shrink-0"></i>
        </a>
        {% endfor %}
    </div>
    {% else %}
    <div class="border-l-4 border-amber-400 bg-ink/3 px-4 py-3">
        <p class="text-sm text-ink-soft">
            <i class="fa-solid fa-circle-exclamation text-amber-500 mr-1.5"></i>
            Vous n'avez aucune pièce validée. Une pièce doit être publiée avant de pouvoir être promue.
        </p>
    </div>
    {% endif %}
</div>
{% endblock main %}
```

- [ ] **Step 6 : Créer promote/templates/promote/sponsor_calendar.html**

```html
{% extends "core/base.html" %}
{% load static %}

{% block title %}Réserver un bandeau — Petites Annonces Théâtre{% endblock %}

{% block main %}
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css">

<div class="max-w-2xl mx-auto px-4 py-10">
    <h1 class="font-display font-bold text-ink text-xl uppercase tracking-[0.06em] mb-2">
        Réserver un bandeau
    </h1>
    <p class="text-ink-soft text-sm mb-8">
        Choisissez votre pièce, une formule et une date de début. Un seul bandeau à la fois — les dates déjà réservées sont grisées.
    </p>

    {% if messages %}
    {% for message in messages %}
    <div class="border-l-4 border-red-400 bg-red-50 px-4 py-3 mb-6">
        <p class="text-sm text-red-700">{{ message }}</p>
    </div>
    {% endfor %}
    {% endif %}

    {% if not selected_play and not plays %}
    <div class="border-l-4 border-amber-400 bg-ink/3 px-4 py-3">
        <p class="text-sm text-ink-soft">
            Vous n'avez aucune pièce validée.
            <a href="{% url 'shows:add_play' %}" class="underline">Ajouter une pièce</a>
        </p>
    </div>
    {% else %}

    {% if not selected_play %}
    <div class="mb-6">
        <label class="block text-xs font-bold uppercase tracking-wider text-ink-soft mb-2">Pièce</label>
        <select id="play-select" class="w-full border border-ink/20 px-3 py-2 text-sm bg-white">
            <option value="">— Choisir une pièce —</option>
            {% for play in plays %}
            <option value="{{ play.pk }}">{{ play.title }}</option>
            {% endfor %}
        </select>
    </div>
    {% else %}

    <form method="post" action="{% url 'promote:sponsor_checkout' selected_play.pk %}" id="checkout-form">
        {% csrf_token %}

        <div class="mb-6 p-4 border border-ink/10 flex items-center gap-3">
            {% if selected_play.poster %}
            <img src="{{ selected_play.poster.url }}" alt="{{ selected_play.title }}"
                 class="w-10 h-14 object-cover shrink-0">
            {% endif %}
            <div>
                <p class="font-display font-bold text-sm uppercase">{{ selected_play.title }}</p>
                {% if selected_play.company %}
                <p class="text-xs text-ink-soft">{{ selected_play.company }}</p>
                {% endif %}
            </div>
            <a href="{% url 'promote:sponsor_list' %}"
               class="ml-auto text-xs text-ink-soft underline">Changer</a>
        </div>

        <div class="mb-6">
            <label class="block text-xs font-bold uppercase tracking-wider text-ink-soft mb-3">Formule</label>
            <div class="grid grid-cols-3 gap-3">
                {% for value, label, price_cents in formula_options %}
                <label class="cursor-pointer">
                    <input type="radio" name="formula" value="{{ value }}"
                           class="sr-only peer" {% if forloop.first %}checked{% endif %}>
                    <div class="border border-ink/15 peer-checked:border-primary peer-checked:bg-primary/5
                                px-4 py-3 text-center transition-colors">
                        <p class="font-bold text-sm">{{ label }}</p>
                        <p class="text-xs text-ink-soft mt-0.5">{{ price_cents|floatformat:0 }} €</p>
                    </div>
                </label>
                {% endfor %}
            </div>
        </div>

        <div class="mb-6">
            <label for="id_start_date"
                   class="block text-xs font-bold uppercase tracking-wider text-ink-soft mb-2">
                Date de début
            </label>
            <input type="text" id="id_start_date" name="start_date"
                   placeholder="Choisir une date…"
                   class="w-full border border-ink/20 px-3 py-2 text-sm bg-white cursor-pointer"
                   readonly>
            <p class="text-xs text-ink-soft mt-1" id="end-date-label"></p>
        </div>

        <button type="submit"
                class="w-full bg-primary text-white font-bold uppercase tracking-wider text-sm py-3
                       hover:opacity-90 transition-opacity disabled:opacity-40"
                id="submit-btn" disabled>
            Payer par carte →
        </button>
    </form>
    {% endif %}
    {% endif %}
</div>

<script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
<script src="https://cdn.jsdelivr.net/npm/flatpickr/dist/l10n/fr.js"></script>
<script>
const FORMULA_DAYS = {day: 0, week: 6, month: 29};
const FORMULA_LABELS_FR = {day: 'jour', week: '7 jours', month: '30 jours'};

{% if not selected_play %}
document.getElementById('play-select').addEventListener('change', function() {
    if (this.value) {
        window.location = '{% url "promote:sponsor_calendar" %}?play=' + this.value;
    }
});
{% else %}
let fp;

function getFormula() {
    const checked = document.querySelector('input[name="formula"]:checked');
    return checked ? checked.value : 'week';
}

function updateEndDate(dateStr) {
    const formula = getFormula();
    if (!dateStr) return;
    const days = FORMULA_DAYS[formula] || 0;
    const start = new Date(dateStr);
    const end = new Date(start);
    end.setDate(end.getDate() + days);
    const opts = {day: 'numeric', month: 'long', year: 'numeric'};
    const endStr = end.toLocaleDateString('fr-FR', opts);
    document.getElementById('end-date-label').textContent = 'Fin : ' + endStr;
    document.getElementById('submit-btn').disabled = false;
}

fetch('{% url "promote:sponsor_availability" %}')
    .then(r => r.json())
    .then(data => {
        const disabled = data.booked.map(b => ({from: b.start, to: b.end}));
        fp = flatpickr('#id_start_date', {
            locale: 'fr',
            minDate: 'today',
            disable: disabled,
            onChange: function(_, dateStr) { updateEndDate(dateStr); },
        });
    });

document.querySelectorAll('input[name="formula"]').forEach(radio => {
    radio.addEventListener('change', function() {
        const dateStr = document.getElementById('id_start_date').value;
        if (dateStr) updateEndDate(dateStr);
    });
});
{% endif %}
</script>
{% endblock main %}
```

**Note :** `formula_options` doit être passé depuis la vue. Mettre à jour `sponsor_calendar` pour passer :

```python
    formula_options = [
        ('day',   'Jour',     3),
        ('week',  'Semaine', 10),
        ('month', 'Mois',    30),
    ]
    return render(request, 'promote/sponsor_calendar.html', {
        'plays': plays,
        'selected_play': selected_play,
        'formula_options': formula_options,
    })
```

- [ ] **Step 7 : Vérifier que les tests passent**

```bash
uv run python manage.py test promote.tests.SponsorListViewTests promote.tests.AvailabilityViewTests
```

Expected: OK (5 tests)

- [ ] **Step 8 : Commit**

```bash
git add promote/urls.py promote/views.py promote/tests.py promote/templates/
git commit -m "feat: add sponsor list, calendar, availability views"
```

---

## Task 4 : Vue checkout — création Promote + session Stripe

**Files:**
- Modify: `promote/views.py`
- Modify: `promote/tests.py`

- [ ] **Step 1 : Écrire les tests**

Ajouter dans `promote/tests.py` :

```python
from unittest.mock import patch, MagicMock


class CheckoutViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            email='checkout@example.com', password='password123'
        )
        self.play = Play.objects.create(
            user=self.user, title='Test Play',
            genre='theatre', moderation_status='published',
        )

    def _mock_session(self):
        session = MagicMock()
        session.id = 'cs_test_abc123'
        session.url = 'https://checkout.stripe.com/pay/cs_test_abc123'
        return session

    @patch('promote.views.stripe')
    def test_checkout_creates_promote_and_redirects(self, mock_stripe):
        mock_stripe.checkout.Session.create.return_value = self._mock_session()
        self.client.login(email='checkout@example.com', password='password123')
        response = self.client.post(
            reverse('promote:sponsor_checkout', args=[self.play.pk]),
            {'formula': 'week', 'start_date': '2026-08-01'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], 'https://checkout.stripe.com/pay/cs_test_abc123')
        promote = Promote.objects.get(stripe_session_id='cs_test_abc123')
        self.assertEqual(promote.status, 'pending_payment')
        self.assertEqual(promote.formula, 'week')

    @patch('promote.views.stripe')
    def test_checkout_rejects_overlapping_slot(self, mock_stripe):
        Promote.objects.create(
            user=self.user, play=self.play, title=self.play.title,
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 7),
            formula='week', status='confirmed',
        )
        self.client.login(email='checkout@example.com', password='password123')
        response = self.client.post(
            reverse('promote:sponsor_checkout', args=[self.play.pk]),
            {'formula': 'week', 'start_date': '2026-08-03'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('calendar', response['Location'])
        self.assertFalse(mock_stripe.checkout.Session.create.called)

    def test_checkout_rejects_non_owner(self):
        other = CustomUser.objects.create_user(
            email='other@example.com', password='password123'
        )
        self.client.login(email='other@example.com', password='password123')
        response = self.client.post(
            reverse('promote:sponsor_checkout', args=[self.play.pk]),
            {'formula': 'week', 'start_date': '2026-09-01'},
        )
        self.assertEqual(response.status_code, 404)

    def test_checkout_rejects_unpublished_play(self):
        self.play.moderation_status = 'pending'
        self.play.save()
        self.client.login(email='checkout@example.com', password='password123')
        response = self.client.post(
            reverse('promote:sponsor_checkout', args=[self.play.pk]),
            {'formula': 'week', 'start_date': '2026-09-01'},
        )
        self.assertEqual(response.status_code, 404)
```

- [ ] **Step 2 : Lancer pour vérifier l'échec**

```bash
uv run python manage.py test promote.tests.CheckoutViewTests
```

Expected: FAIL — `sponsor_checkout` n'existe pas encore.

- [ ] **Step 3 : Ajouter la vue checkout dans promote/views.py**

Ajouter après `sponsor_availability` :

```python
@login_required
def sponsor_checkout(request, play_id):
    import stripe as stripe_lib
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

    stripe_lib.api_key = settings.STRIPE_SECRET_KEY
    session = stripe_lib.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'eur',
                'unit_amount': FORMULA_PRICES[formula],
                'product_data': {
                    'name': f"Bandeau — {play.title} ({FORMULA_LABELS[formula]})",
                },
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url=(
            f"{settings.SITE_URL}/promote/sponsor/confirmation/{{CHECKOUT_SESSION_ID}}/"
        ),
        cancel_url=f"{settings.SITE_URL}/promote/sponsor/cancel/",
        metadata={'promote_id': str(promote.pk)},
        customer_email=request.user.email,
    )

    promote.stripe_session_id = session.id
    promote.save(update_fields=['stripe_session_id'])

    return redirect(session.url)
```

**Note :** `import stripe as stripe_lib` est fait localement pour permettre le mock dans les tests via `@patch('promote.views.stripe')`. Ajouter également `import stripe` au niveau module en haut de `promote/views.py` (après les imports existants) :

```python
import stripe
```

Puis dans `sponsor_checkout`, remplacer `import stripe as stripe_lib` et `stripe_lib.` par `stripe.` directement (le mock `@patch('promote.views.stripe')` fonctionne sur l'import module-level).

- [ ] **Step 4 : Vérifier que les tests passent**

```bash
uv run python manage.py test promote.tests.CheckoutViewTests
```

Expected: OK (4 tests)

- [ ] **Step 5 : Commit**

```bash
git add promote/views.py promote/tests.py
git commit -m "feat: add sponsor checkout view with Stripe session creation"
```

---

## Task 5 : Webhook Stripe

**Files:**
- Modify: `promote/views.py`
- Modify: `promote/tests.py`

- [ ] **Step 1 : Écrire les tests**

Ajouter dans `promote/tests.py` :

```python
class WebhookViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            email='webhook@example.com', password='password123'
        )
        self.play = Play.objects.create(
            user=self.user, title='Webhook Play',
            genre='theatre', moderation_status='published',
        )
        self.promote = Promote.objects.create(
            user=self.user, play=self.play, title=self.play.title,
            start_date=date(2026, 9, 1), end_date=date(2026, 9, 7),
            formula='week', status='pending_payment',
            stripe_session_id='cs_test_webhook',
        )

    def _post_webhook(self, event):
        with patch('promote.views.stripe') as mock_stripe:
            mock_stripe.Webhook.construct_event.return_value = event
            response = self.client.post(
                reverse('promote:stripe_webhook'),
                data=b'{}',
                content_type='application/json',
                HTTP_STRIPE_SIGNATURE='t=1,v1=abc',
            )
        return response

    def test_webhook_confirms_promote_on_completed(self):
        event = {
            'type': 'checkout.session.completed',
            'data': {'object': {
                'metadata': {'promote_id': str(self.promote.pk)},
                'amount_total': 1000,
            }},
        }
        response = self._post_webhook(event)
        self.assertEqual(response.status_code, 200)
        self.promote.refresh_from_db()
        self.assertEqual(self.promote.status, 'confirmed')
        self.assertEqual(float(self.promote.price_paid), 10.0)

    def test_webhook_returns_200_on_invalid_signature(self):
        with patch('promote.views.stripe') as mock_stripe:
            mock_stripe.Webhook.construct_event.side_effect = Exception("invalid sig")
            response = self.client.post(
                reverse('promote:stripe_webhook'),
                data=b'bad',
                content_type='application/json',
                HTTP_STRIPE_SIGNATURE='bad',
            )
        self.assertEqual(response.status_code, 200)

    def test_webhook_ignores_other_events(self):
        event = {
            'type': 'payment_intent.created',
            'data': {'object': {}},
        }
        response = self._post_webhook(event)
        self.assertEqual(response.status_code, 200)
        self.promote.refresh_from_db()
        self.assertEqual(self.promote.status, 'pending_payment')

    def test_webhook_skips_confirm_on_overlap(self):
        other_play = Play.objects.create(
            user=self.user, title='Other Play',
            genre='theatre', moderation_status='published',
        )
        Promote.objects.create(
            user=self.user, play=other_play, title='Other',
            start_date=date(2026, 9, 3), end_date=date(2026, 9, 5),
            formula='day', status='confirmed',
        )
        event = {
            'type': 'checkout.session.completed',
            'data': {'object': {
                'metadata': {'promote_id': str(self.promote.pk)},
                'amount_total': 1000,
            }},
        }
        response = self._post_webhook(event)
        self.assertEqual(response.status_code, 200)
        self.promote.refresh_from_db()
        self.assertEqual(self.promote.status, 'pending_payment')
```

- [ ] **Step 2 : Lancer pour vérifier l'échec**

```bash
uv run python manage.py test promote.tests.WebhookViewTests
```

Expected: FAIL — `stripe_webhook` n'existe pas encore.

- [ ] **Step 3 : Ajouter la vue webhook dans promote/views.py**

Ajouter après `sponsor_checkout` :

```python
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        logger.error("Stripe webhook signature error: %s", e)
        return HttpResponse(status=200)

    if event.get('type') == 'checkout.session.completed':
        session = event['data']['object']
        promote_id = session.get('metadata', {}).get('promote_id')

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
                    promote.price_paid = session.get('amount_total', 0) / 100
                    promote.save(update_fields=['status', 'price_paid'])

            except Promote.DoesNotExist:
                logger.error("Webhook: Promote %s not found", promote_id)

    return HttpResponse(status=200)
```

- [ ] **Step 4 : Vérifier que les tests passent**

```bash
uv run python manage.py test promote.tests.WebhookViewTests
```

Expected: OK (4 tests)

- [ ] **Step 5 : Commit**

```bash
git add promote/views.py promote/tests.py
git commit -m "feat: add Stripe webhook confirming Promote on payment"
```

---

## Task 6 : Pages confirmation + annulation

**Files:**
- Modify: `promote/views.py`
- Modify: `promote/tests.py`
- Create: `promote/templates/promote/sponsor_confirmation.html`
- Create: `promote/templates/promote/sponsor_cancel.html`

- [ ] **Step 1 : Écrire les tests**

Ajouter dans `promote/tests.py` :

```python
class ConfirmationViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            email='conf@example.com', password='password123'
        )
        self.play = Play.objects.create(
            user=self.user, title='Conf Play',
            genre='theatre', moderation_status='published',
        )
        self.promote = Promote.objects.create(
            user=self.user, play=self.play, title=self.play.title,
            start_date=date(2026, 10, 1), end_date=date(2026, 10, 7),
            formula='week', status='confirmed',
            stripe_session_id='cs_test_confirm123',
            price_paid='10.00',
        )

    def test_confirmation_shows_promote_details(self):
        self.client.login(email='conf@example.com', password='password123')
        response = self.client.get(
            reverse('promote:sponsor_confirmation', args=['cs_test_confirm123'])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Conf Play')

    def test_confirmation_requires_ownership(self):
        other = CustomUser.objects.create_user(
            email='other2@example.com', password='password123'
        )
        self.client.login(email='other2@example.com', password='password123')
        response = self.client.get(
            reverse('promote:sponsor_confirmation', args=['cs_test_confirm123'])
        )
        self.assertEqual(response.status_code, 404)

    def test_cancel_page_renders(self):
        self.client.login(email='conf@example.com', password='password123')
        response = self.client.get(reverse('promote:sponsor_cancel'))
        self.assertEqual(response.status_code, 200)
```

- [ ] **Step 2 : Lancer pour vérifier l'échec**

```bash
uv run python manage.py test promote.tests.ConfirmationViewTests
```

Expected: FAIL.

- [ ] **Step 3 : Ajouter les vues dans promote/views.py**

```python
@login_required
def sponsor_confirmation(request, session_id):
    promote = get_object_or_404(
        Promote, stripe_session_id=session_id, user=request.user
    )
    today = date.today()
    is_active = promote.start_date <= today <= promote.end_date
    return render(request, 'promote/sponsor_confirmation.html', {
        'promote': promote,
        'is_active': is_active,
    })


@login_required
def sponsor_cancel(request):
    return render(request, 'promote/sponsor_cancel.html')
```

- [ ] **Step 4 : Créer promote/templates/promote/sponsor_confirmation.html**

```html
{% extends "core/base.html" %}

{% block title %}Réservation confirmée — Petites Annonces Théâtre{% endblock %}

{% block main %}
<div class="max-w-2xl mx-auto px-4 py-10">
    <div class="border-l-4 border-green-400 bg-ink/3 px-4 py-3 mb-8">
        <p class="text-sm font-bold text-green-700 mb-1">
            <i class="fa-solid fa-circle-check text-green-500 mr-1.5"></i>
            Paiement confirmé !
        </p>
        <p class="text-sm text-ink-soft">
            Votre bandeau est réservé. Merci pour votre soutien à la plateforme.
        </p>
    </div>

    <div class="border border-ink/10 p-6 space-y-3">
        <div class="flex gap-4 items-start">
            {% if promote.play and promote.play.poster %}
            <img src="{{ promote.play.poster.url }}"
                 alt="{{ promote.play.title }}"
                 class="w-14 h-20 object-cover shrink-0">
            {% endif %}
            <div>
                <p class="font-display font-bold text-ink text-base uppercase tracking-wide">
                    {{ promote.play.title }}
                </p>
                {% if promote.play.company %}
                <p class="text-ink-soft text-sm mt-0.5">{{ promote.play.company }}</p>
                {% endif %}
            </div>
        </div>
        <div class="text-sm text-ink-soft space-y-1 pt-2 border-t border-ink/8">
            <p><span class="font-medium text-ink">Formule :</span> {{ promote.get_formula_display }}</p>
            <p>
                <span class="font-medium text-ink">Période :</span>
                du {{ promote.start_date|date:"j F Y" }} au {{ promote.end_date|date:"j F Y" }}
            </p>
            {% if promote.price_paid %}
            <p><span class="font-medium text-ink">Montant :</span> {{ promote.price_paid }} €</p>
            {% endif %}
        </div>
    </div>

    <div class="mt-6 flex gap-3">
        {% if is_active %}
        <a href="{% url 'index' %}"
           class="px-4 py-2 bg-primary text-white text-sm font-bold uppercase tracking-wider
                  hover:opacity-90 transition-opacity">
            Voir le bandeau →
        </a>
        {% endif %}
        <a href="{% url 'shows:play_detail' promote.play.pk %}"
           class="px-4 py-2 border border-ink/20 text-ink-soft text-sm font-bold uppercase
                  tracking-wider hover:border-ink hover:text-ink transition-colors">
            Voir la pièce
        </a>
    </div>
</div>
{% endblock main %}
```

- [ ] **Step 5 : Créer promote/templates/promote/sponsor_cancel.html**

```html
{% extends "core/base.html" %}

{% block title %}Paiement annulé — Petites Annonces Théâtre{% endblock %}

{% block main %}
<div class="max-w-2xl mx-auto px-4 py-10">
    <div class="border-l-4 border-ink/15 bg-ink/3 px-4 py-3 mb-8">
        <p class="text-sm text-ink-soft">
            <i class="fa-solid fa-circle-xmark text-ink/40 mr-1.5"></i>
            Paiement annulé — aucun montant n'a été débité.
        </p>
    </div>
    <a href="{% url 'promote:sponsor_list' %}"
       class="px-4 py-2 border border-ink/20 text-ink-soft text-sm font-bold uppercase
              tracking-wider hover:border-ink hover:text-ink transition-colors">
        ← Retour
    </a>
</div>
{% endblock main %}
```

- [ ] **Step 6 : Vérifier que les tests passent**

```bash
uv run python manage.py test promote.tests.ConfirmationViewTests
```

Expected: OK (3 tests)

- [ ] **Step 7 : Lancer toute la suite promote**

```bash
uv run python manage.py test promote
```

Expected: OK (tous les tests)

- [ ] **Step 8 : Commit**

```bash
git add promote/views.py promote/tests.py promote/templates/
git commit -m "feat: add sponsor confirmation and cancel pages"
```

---

## Task 7 : Bandeau générique + mise à jour core/views.index + index.html

**Files:**
- Create: `promote/templates/promote/banner_play.html`
- Modify: `core/views.py` (lignes 98–106)
- Modify: `core/templates/core/index.html` (lignes 57–60)
- Modify: `promote/tests.py`

- [ ] **Step 1 : Écrire les tests**

Ajouter dans `promote/tests.py` :

```python
from django.utils import timezone as tz


class IndexBannerTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            email='banner@example.com', password='password123'
        )
        self.play = Play.objects.create(
            user=self.user, title='Banner Play',
            genre='theatre', moderation_status='published',
        )

    def test_index_uses_confirmed_play_promo(self):
        today = date.today()
        Promote.objects.create(
            user=self.user, play=self.play, title=self.play.title,
            start_date=today, end_date=today + timedelta(days=6),
            formula='week', status='confirmed',
        )
        response = self.client.get(reverse('index'))
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context.get('promo'))
        self.assertEqual(response.context['promo'].play, self.play)

    def test_index_ignores_pending_payment_promo(self):
        today = date.today()
        Promote.objects.create(
            user=self.user, play=self.play, title=self.play.title,
            start_date=today, end_date=today + timedelta(days=6),
            formula='week', status='pending_payment',
        )
        response = self.client.get(reverse('index'))
        promo = response.context.get('promo')
        # promo may be None or a legacy 'your-ad' slug — not the pending_payment one
        if promo:
            self.assertNotEqual(promo.status, 'pending_payment')
```

- [ ] **Step 2 : Lancer pour vérifier l'échec**

```bash
uv run python manage.py test promote.tests.IndexBannerTests
```

Expected: FAIL — la logique actuelle ne filtre pas par `status`.

- [ ] **Step 3 : Mettre à jour core/views.py**

Trouver le bloc autour des lignes 98–106 (dans la vue `index`) :

```python
    today = date.today()
    promo = Promote.objects.filter(start_date__lte=today, end_date__gte=today).order_by('?').first()
    if promo:
        Promote.objects.filter(pk=promo.pk).update(impression_count=F("impression_count") + 1)
    else:
        promo = Promote.objects.filter(slug__exact='your-ad').first()

    ctx['promo'] = promo
```

Remplacer par :

```python
    from django.utils import timezone as _tz
    today = date.today()

    active_confirmed = Promote.objects.filter(
        status='confirmed',
        start_date__lte=today,
        end_date__gte=today,
    )
    # Play-based promos (self-service) take priority
    promo = (
        active_confirmed
        .filter(play__isnull=False)
        .order_by('start_date')
        .select_related('play')
        .first()
    )
    if not promo:
        promo = active_confirmed.filter(play__isnull=True).order_by('?').first()
    if not promo:
        promo = Promote.objects.filter(slug__exact='your-ad').first()

    if promo:
        Promote.objects.filter(pk=promo.pk).update(impression_count=F("impression_count") + 1)

    promo_next_rep = None
    if promo and promo.play_id:
        promo_next_rep = (
            promo.play.representations
            .filter(datetime__gte=_tz.now())
            .order_by('datetime')
            .first()
        )

    ctx['promo'] = promo
    ctx['promo_next_rep'] = promo_next_rep
```

- [ ] **Step 4 : Créer promote/templates/promote/banner_play.html**

```html
{% load static %}
<a href="{% url 'shows:play_detail' promo.play.pk %}"
   class="group flex items-stretch mb-6 bg-primary hover:opacity-90 transition-opacity">

    {% if promo.play.poster %}
    <div class="w-16 sm:w-20 shrink-0">
        <img src="{{ promo.play.poster.url }}"
             alt="Affiche {{ promo.play.title }}"
             width="80" height="112"
             class="w-full h-full object-cover"
             style="min-height: 88px; display: block;">
    </div>
    {% endif %}

    <div class="flex flex-1 items-center justify-between px-4 py-3 gap-3 min-w-0">
        <div class="min-w-0">
            <span class="font-display text-[9px] font-bold uppercase tracking-[0.20em] text-white/25 block mb-1.5">
                Publicité
            </span>
            <p class="font-display font-bold text-white text-sm sm:text-base leading-tight uppercase tracking-wide truncate">
                {{ promo.play.title }}
            </p>
            {% if promo.play.company %}
            <p class="text-white/50 text-xs mt-1 hidden sm:block italic">
                {{ promo.play.company }}
            </p>
            {% endif %}
            {% if promo_next_rep %}
            <p class="text-white/35 text-[11px] mt-1">
                {% if promo_next_rep.venue %}{{ promo_next_rep.venue }}{% endif %}
                {% if promo_next_rep.city %} — {{ promo_next_rep.city }}{% endif %}
                · <time datetime="{{ promo_next_rep.datetime|date:'Y-m-d' }}">
                    {{ promo_next_rep.datetime|date:"j M." }}
                </time>
            </p>
            {% endif %}
        </div>
        <span class="shrink-0 font-display text-[10px] font-bold uppercase tracking-[0.12em]
                     border border-white/20 text-white/40 group-hover:border-white/50
                     group-hover:text-white px-3 py-1.5 transition-colors whitespace-nowrap">
            En savoir plus →
        </span>
    </div>
</a>
```

- [ ] **Step 5 : Mettre à jour core/templates/core/index.html**

Trouver le bloc bannière (lignes ~57–60) :

```html
    <!-- Bannière promo -->
    {% with "promote/banner_"|add:promo.slug|add:".html" as template_name %}
        {% include template_name %}
    {% endwith %}
```

Remplacer par :

```html
    <!-- Bannière promo -->
    {% if promo %}
    {% if promo.play %}
        {% include "promote/banner_play.html" %}
    {% else %}
        {% with "promote/banner_"|add:promo.slug|add:".html" as template_name %}
            {% include template_name %}
        {% endwith %}
    {% endif %}
    {% endif %}
```

- [ ] **Step 6 : Vérifier que les tests passent**

```bash
uv run python manage.py test promote.tests.IndexBannerTests
```

Expected: OK (2 tests)

- [ ] **Step 7 : Lancer la suite complète**

```bash
uv run python manage.py test
```

Expected: OK (tous les tests)

- [ ] **Step 8 : Commit**

```bash
git add promote/templates/promote/banner_play.html core/views.py core/templates/core/index.html promote/tests.py
git commit -m "feat: add banner_play.html and update index banner selection to prioritise confirmed play promos"
```

---

## Task 8 : Bouton « Promouvoir » sur play_detail + mise à jour admin

**Files:**
- Modify: `shows/templates/shows/partials/play_owner_zone.html`
- Modify: `promote/admin.py`

Pas de tests unitaires — vérification manuelle dans le navigateur et dans l'admin.

- [ ] **Step 1 : Ajouter le bouton « Promouvoir » dans play_owner_zone.html**

Ouvrir `shows/templates/shows/partials/play_owner_zone.html`. Trouver le bloc `{% else %}` des boutons actifs (Modifier / Supprimer) et ajouter le bouton Promouvoir entre les deux :

```html
    {% else %}
    <div class="flex flex-wrap gap-2">
        <a href="{% url 'shows:edit_play' pk=play.pk %}"
           class="flex items-center gap-2 px-4 py-2
                  text-[11px] font-bold uppercase tracking-[0.12em]
                  border border-ink/20 text-ink-soft hover:border-ink hover:text-ink transition-colors">
            <i class="fa-solid fa-pen text-[10px]"></i>Modifier
        </a>

        {% if play.moderation_status == 'published' %}
        <a href="{% url 'promote:sponsor_list' %}?play={{ play.pk }}"
           class="flex items-center gap-2 px-4 py-2
                  text-[11px] font-bold uppercase tracking-[0.12em]
                  border border-primary/40 text-primary hover:border-primary hover:bg-primary/5
                  transition-colors">
            <i class="fa-solid fa-star text-[10px]"></i>Promouvoir
        </a>
        {% else %}
        <span title="Votre pièce doit être validée avant de pouvoir être promue."
              class="flex items-center gap-2 px-4 py-2
                     text-[11px] font-bold uppercase tracking-[0.12em]
                     border border-ink/10 bg-ink/3 text-ink/25 cursor-not-allowed select-none">
            <i class="fa-solid fa-star text-[10px]"></i>Promouvoir
        </span>
        {% endif %}

        <a href="{% url 'shows:delete_play' pk=play.pk %}"
           class="flex items-center gap-2 px-4 py-2
                  text-[11px] font-bold uppercase tracking-[0.12em]
                  text-red-400 hover:text-red-600 hover:bg-red-50
                  border border-transparent hover:border-red-200 transition-colors ml-auto">
            <i class="fa-solid fa-trash text-[10px]"></i>Supprimer
        </a>
    </div>
    {% endif %}
```

- [ ] **Step 2 : Mettre à jour promote/admin.py**

Remplacer le contenu complet :

```python
from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _
from .models import Promote


@admin.register(Promote)
class PromoteAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'title', 'play', 'status', 'formula',
        'start_date', 'end_date', 'price_paid', 'user',
        'impression_count', 'click_count', 'ctr',
    )
    list_filter  = ('status', 'formula', 'start_date')
    search_fields = ('title', 'user__email', 'play__title')
    date_hierarchy = 'start_date'
    ordering = ('-created_at',)
    readonly_fields = (
        'impression_count', 'click_count', 'detail_view_count',
        'booking_click_count', 'duration_display', 'ctr',
        'created_at', 'updated_at',
    )
    prepopulated_fields = {'slug': ('title',)}
    actions = ('marquer_expire',)

    fieldsets = (
        (_('Informations générales'), {
            'fields': (('title', 'slug'), 'user', 'play'),
        }),
        (_('Stripe'), {
            'fields': ('status', 'formula', 'stripe_session_id', 'price_paid'),
        }),
        (_('Période de diffusion'), {
            'fields': (('start_date', 'end_date'), 'duration_display'),
        }),
        (_('Statistiques'), {
            'classes': ('collapse',),
            'fields': (
                ('impression_count', 'click_count', 'ctr'),
                ('detail_view_count', 'booking_click_count'),
            ),
        }),
        (_('Métadonnées'), {
            'classes': ('collapse',),
            'fields': (('created_at', 'updated_at'),),
        }),
    )

    @admin.display(description='Durée (j)')
    def duration_display(self, obj):
        return obj.duration_days

    @admin.display(description='CTR')
    def ctr(self, obj):
        if obj.impression_count:
            return f"{obj.click_count / obj.impression_count * 100:.1f} %"
        return '—'

    @admin.action(description=_('Marquer comme expirées'))
    def marquer_expire(self, request, queryset):
        updated = queryset.update(status='expired')
        self.message_user(
            request, _('%d bandeau(x) marqué(s) comme expiré(s).') % updated,
            level=messages.WARNING,
        )
```

- [ ] **Step 3 : Vérifier**

```bash
uv run python manage.py check
uv run python manage.py test
```

Expected: System check identified no issues. All tests pass.

- [ ] **Step 4 : Commit**

```bash
git add shows/templates/shows/partials/play_owner_zone.html promote/admin.py
git commit -m "feat: add Promote button on play_detail owner zone and update PromoteAdmin"
```

---

## Vérification finale

- [ ] `uv run python manage.py test` → tous les tests passent ✓
- [ ] `uv run python manage.py check` → aucune erreur ✓
- [ ] Créer une pièce publiée → bouton "Promouvoir" visible ✓
- [ ] Cliquer "Promouvoir" → page liste → calendrier avec Flatpickr ✓
- [ ] Soumettre le formulaire → redirect Stripe Checkout (en mode test) ✓
- [ ] Webhook reçu → `status='confirmed'` dans l'admin ✓
- [ ] Page d'accueil → banner_play.html affiché à la place du slug-based banner ✓
- [ ] Ancien bandeau manuel toujours fonctionnel (rétrocompatibilité) ✓
