# Modération des Pièces — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Appliquer le même pipeline de modération automatique (Mistral texte + NudeNet images) aux pièces (`Play`) qu'aux offres (`Offer`), afin qu'une pièce validée puisse être promue via Stripe.

**Architecture:** Ajout de `moderation_status` + FK `moderation` sur `Play`. Tâche Celery `moderate_play` déclenchée à la création et à la modification des champs modérés (titre, description, poster, cover_image). Les pièces non publiées sont inaccessibles publiquement.

**Tech Stack:** Django 5.1, Celery, Mistral AI (texte), NudeNet (images), SQLite (tests), pytest via `python manage.py test`

---

## Structure des fichiers

| Fichier | Action |
|---------|--------|
| `shows/models.py` | Ajouter `moderation_status` (CharField) + `moderation` (FK ModerationResult) |
| `shows/migrations/XXXX_add_play_moderation.py` | Généré par makemigrations |
| `core/services/image_moderation.py` | Ajouter `moderate_play_images(play)` |
| `core/tasks.py` | Ajouter `moderate_play(play_id)` |
| `shows/views.py` | Déclencher `moderate_play` dans `add_play` et `edit_play` ; restreindre `play_detail` |
| `shows/admin.py` | Filtres, colonnes, actions valider/rejeter |
| `shows/templates/shows/play_detail.html` | Bandeau statut modération pour le propriétaire |
| `shows/tests.py` | Tests TDD |
| `core/tests.py` | Corriger le test cassé (`passed=True` supprimé de ModerationResult) |

---

## Task 1 : Corriger le test cassé + ajouter les champs au modèle Play

**Files:**
- Modify: `core/tests.py:48`
- Modify: `shows/models.py`
- Create: migration (via makemigrations)
- Test: `shows/tests.py`

- [ ] **Step 1 : Corriger le test cassé dans core/tests.py**

Le champ `passed` a été supprimé de `ModerationResult`. La ligne 48 de `core/tests.py` plante :

```python
# Remplacer :
moderation = ModerationResult.objects.create(passed=True, reasons='')
# Par :
moderation = ModerationResult.objects.create(reasons='')
```

- [ ] **Step 2 : Vérifier que le test passe**

```bash
uv run python manage.py test core.tests.OfferModelTests.test_get_moderation_text_omits_empty_fields
```

Expected: OK

- [ ] **Step 3 : Écrire les tests du modèle Play**

Dans `shows/tests.py` :

```python
from django.test import TestCase
from accounts.models import CustomUser
from shows.models import Play


class PlayModerationStatusTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email='tester@example.com',
            password='password123',
        )

    def test_default_moderation_status_is_pending(self):
        play = Play.objects.create(
            user=self.user,
            title='Test Play',
            genre='theatre',
        )
        self.assertEqual(play.moderation_status, 'pending')

    def test_moderation_status_choices(self):
        play = Play.objects.create(
            user=self.user,
            title='Test Play',
            genre='theatre',
        )
        for status in ('pending', 'published', 'under_review', 'rejected'):
            play.moderation_status = status
            play.save()
            play.refresh_from_db()
            self.assertEqual(play.moderation_status, status)

    def test_moderation_fk_nullable(self):
        play = Play.objects.create(
            user=self.user,
            title='Test Play',
            genre='theatre',
        )
        self.assertIsNone(play.moderation)
```

- [ ] **Step 4 : Lancer les tests pour vérifier qu'ils échouent**

```bash
uv run python manage.py test shows.tests.PlayModerationStatusTests
```

Expected: FAIL — `Play` n'a pas encore `moderation_status`

- [ ] **Step 5 : Ajouter les champs à shows/models.py**

Dans `shows/models.py`, après les imports, ajouter les constantes et les champs au modèle `Play` :

```python
# En haut du fichier, après les imports existants :
from moderation.models import ModerationResult
```

Dans la classe `Play`, après `updated_at` :

```python
    # --- Modération ---
    PENDING      = 'pending'
    PUBLISHED    = 'published'
    UNDER_REVIEW = 'under_review'
    REJECTED     = 'rejected'
    MODERATION_STATUS_CHOICES = [
        (PENDING,      'En vérification'),
        (PUBLISHED,    'Publiée'),
        (UNDER_REVIEW, 'Sous examen'),
        (REJECTED,     'Rejetée'),
    ]

    moderation_status = models.CharField(
        max_length=20,
        choices=MODERATION_STATUS_CHOICES,
        default=PENDING,
    )
    moderation = models.ForeignKey(
        ModerationResult,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='plays',
    )
```

- [ ] **Step 6 : Créer et appliquer la migration**

```bash
uv run python manage.py makemigrations shows --name add_play_moderation
uv run python manage.py migrate
```

Expected: `Applying shows.XXXX_add_play_moderation... OK`

- [ ] **Step 7 : Vérifier que les tests passent**

```bash
uv run python manage.py test shows.tests.PlayModerationStatusTests
```

Expected: OK (3 tests)

- [ ] **Step 8 : Commit**

```bash
git add shows/models.py shows/migrations/ shows/tests.py core/tests.py
git commit -m "feat: add moderation_status + moderation FK to Play model"
```

---

## Task 2 : Ajouter `moderate_play_images` dans image_moderation.py

**Files:**
- Modify: `core/services/image_moderation.py`
- Test: `shows/tests.py`

- [ ] **Step 1 : Écrire le test**

Ajouter dans `shows/tests.py` :

```python
from unittest.mock import patch, MagicMock


class ModeratePlayImagesTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email='tester2@example.com',
            password='password123',
        )

    def test_no_images_returns_passed(self):
        from core.services.image_moderation import moderate_play_images
        play = Play.objects.create(
            user=self.user, title='No Images', genre='theatre'
        )
        passed, reasons = moderate_play_images(play)
        self.assertTrue(passed)
        self.assertEqual(reasons, '')

    @patch('core.services.image_moderation._download_to_temp')
    @patch('core.services.image_moderation._analyze_image_file')
    def test_safe_poster_returns_passed(self, mock_analyze, mock_download):
        from core.services.image_moderation import moderate_play_images
        mock_download.return_value = '/tmp/fake.webp'
        mock_analyze.return_value = True

        play = Play.objects.create(
            user=self.user, title='Safe Poster', genre='theatre'
        )
        # Simuler un poster sans vraiment uploader
        play.poster = MagicMock()
        play.poster.name = 'poster.webp'

        passed, reasons = moderate_play_images(play)
        self.assertTrue(passed)

    @patch('core.services.image_moderation._download_to_temp')
    @patch('core.services.image_moderation._analyze_image_file')
    def test_unsafe_poster_returns_failed(self, mock_analyze, mock_download):
        from core.services.image_moderation import moderate_play_images
        mock_download.return_value = '/tmp/fake.webp'
        mock_analyze.return_value = False  # unsafe

        play = Play.objects.create(
            user=self.user, title='Unsafe Poster', genre='theatre'
        )
        play.poster = MagicMock()
        play.poster.name = 'poster.webp'

        passed, reasons = moderate_play_images(play)
        self.assertFalse(passed)
        self.assertIn('poster', reasons)
```

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

```bash
uv run python manage.py test shows.tests.ModeratePlayImagesTests
```

Expected: FAIL — `moderate_play_images` n'existe pas encore

- [ ] **Step 3 : Implémenter `moderate_play_images` dans core/services/image_moderation.py**

Ajouter à la fin du fichier :

```python
def moderate_play_images(play) -> tuple[bool, str]:
    """
    Analyzes poster and cover_image of a Play.
    Returns (passed: bool, reasons: str).
    """
    flagged = []
    temp_files = []

    images_to_check = []
    if play.poster:
        images_to_check.append(("poster", play.poster))
    if play.cover_image:
        images_to_check.append(("cover_image", play.cover_image))

    if not images_to_check:
        return True, ""

    try:
        for label, image_field in images_to_check:
            temp_path = _download_to_temp(image_field)
            if temp_path:
                temp_files.append(temp_path)
                if not _analyze_image_file(temp_path):
                    flagged.append(label)
    finally:
        for path in temp_files:
            try:
                os.unlink(path)
            except OSError:
                pass

    passed = len(flagged) == 0
    reasons = ",".join(flagged)
    return passed, reasons
```

- [ ] **Step 4 : Vérifier que les tests passent**

```bash
uv run python manage.py test shows.tests.ModeratePlayImagesTests
```

Expected: OK (3 tests)

- [ ] **Step 5 : Commit**

```bash
git add core/services/image_moderation.py shows/tests.py
git commit -m "feat: add moderate_play_images function"
```

---

## Task 3 : Ajouter la tâche Celery `moderate_play`

**Files:**
- Modify: `core/tasks.py`
- Test: `shows/tests.py`

- [ ] **Step 1 : Écrire les tests**

Ajouter dans `shows/tests.py` :

```python
from unittest.mock import patch, MagicMock
from moderation.models import ModerationResult


class ModeratePlayTaskTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email='task_tester@example.com',
            password='password123',
        )

    def _make_play(self):
        return Play.objects.create(
            user=self.user,
            title='Test Play',
            description='Une description de test',
            genre='theatre',
        )

    @patch('core.services.image_moderation.moderate_play_images')
    @patch('moderation.services.moderate_text')
    def test_published_when_text_and_images_pass(self, mock_text, mock_images):
        from core.tasks import moderate_play
        mock_text.return_value = ModerationResult.objects.create(reasons=None)
        mock_images.return_value = (True, '')

        play = self._make_play()
        moderate_play(play.pk)

        play.refresh_from_db()
        self.assertEqual(play.moderation_status, 'published')
        self.assertIsNotNone(play.moderation)

    @patch('core.services.image_moderation.moderate_play_images')
    @patch('moderation.services.moderate_text')
    def test_under_review_when_text_fails(self, mock_text, mock_images):
        from core.tasks import moderate_play
        mock_text.return_value = ModerationResult.objects.create(reasons='violence')
        mock_images.return_value = (True, '')

        play = self._make_play()
        moderate_play(play.pk)

        play.refresh_from_db()
        self.assertEqual(play.moderation_status, 'under_review')

    @patch('core.services.image_moderation.moderate_play_images')
    @patch('moderation.services.moderate_text')
    def test_under_review_when_images_fail(self, mock_text, mock_images):
        from core.tasks import moderate_play
        mock_text.return_value = ModerationResult.objects.create(reasons=None)
        mock_images.return_value = (False, 'poster')

        play = self._make_play()
        moderate_play(play.pk)

        play.refresh_from_db()
        self.assertEqual(play.moderation_status, 'under_review')

    def test_does_not_raise_on_missing_play(self):
        from core.tasks import moderate_play
        # Should log warning and return, not raise
        moderate_play(99999)
```

- [ ] **Step 2 : Lancer pour vérifier l'échec**

```bash
uv run python manage.py test shows.tests.ModeratePlayTaskTests
```

Expected: FAIL — `moderate_play` n'existe pas dans `core/tasks.py`

- [ ] **Step 3 : Implémenter `moderate_play` dans core/tasks.py**

Ajouter après la tâche `moderate_offer` existante :

```python
@shared_task(
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=60,
    retry_jitter=True,
)
def moderate_play(play_id: int):
    from shows.models import Play
    from core.services.image_moderation import moderate_play_images
    from moderation.services import moderate_text

    try:
        play = Play.objects.select_related('moderation').get(pk=play_id)
    except Play.DoesNotExist:
        logger.warning("moderate_play: Play %s not found", play_id)
        return

    try:
        text_result = moderate_text(f"{play.title}\n{play.description or ''}")

        images_ok, image_reasons = moderate_play_images(play)

        text_result.images_passed = images_ok
        text_result.image_reasons = image_reasons
        text_result.save()

        play.moderation = text_result

        if not text_result.reasons and images_ok:
            play.moderation_status = Play.PUBLISHED
        else:
            play.moderation_status = Play.UNDER_REVIEW

        play.save(update_fields=['moderation', 'moderation_status'])

    except Exception as e:
        logger.error("moderate_play failed for play %s: %s", play_id, e)
        if moderate_play.request.retries >= moderate_play.max_retries:
            try:
                play.moderation_status = Play.UNDER_REVIEW
                play.save(update_fields=['moderation_status'])
            except Exception:
                pass
        raise
```

- [ ] **Step 4 : Vérifier que les tests passent**

```bash
uv run python manage.py test shows.tests.ModeratePlayTaskTests
```

Expected: OK (4 tests)

- [ ] **Step 5 : Commit**

```bash
git add core/tasks.py shows/tests.py
git commit -m "feat: add moderate_play Celery task"
```

---

## Task 4 : Déclencher la modération dans les vues + restreindre l'accès public

**Files:**
- Modify: `shows/views.py`
- Test: `shows/tests.py`

- [ ] **Step 1 : Écrire les tests**

Ajouter dans `shows/tests.py` :

```python
from django.test import TestCase, Client
from django.urls import reverse


class PlayViewModerationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = CustomUser.objects.create_user(
            email='owner@example.com', password='password123'
        )
        self.other = CustomUser.objects.create_user(
            email='other@example.com', password='password123'
        )

    def _make_published_play(self):
        return Play.objects.create(
            user=self.owner, title='Published Play',
            genre='theatre', moderation_status='published'
        )

    def _make_pending_play(self):
        return Play.objects.create(
            user=self.owner, title='Pending Play',
            genre='theatre', moderation_status='pending'
        )

    def test_published_play_accessible_to_anyone(self):
        play = self._make_published_play()
        response = self.client.get(reverse('shows:play_detail', args=[play.pk]))
        self.assertEqual(response.status_code, 200)

    def test_pending_play_returns_404_to_non_owner(self):
        play = self._make_pending_play()
        self.client.login(email='other@example.com', password='password123')
        response = self.client.get(reverse('shows:play_detail', args=[play.pk]))
        self.assertEqual(response.status_code, 404)

    def test_pending_play_accessible_to_owner(self):
        play = self._make_pending_play()
        self.client.login(email='owner@example.com', password='password123')
        response = self.client.get(reverse('shows:play_detail', args=[play.pk]))
        self.assertEqual(response.status_code, 200)

    def test_anonymous_gets_404_for_pending_play(self):
        play = self._make_pending_play()
        response = self.client.get(reverse('shows:play_detail', args=[play.pk]))
        self.assertEqual(response.status_code, 404)

    @patch('core.tasks.moderate_play.delay')
    def test_add_play_triggers_moderation(self, mock_delay):
        self.client.login(email='owner@example.com', password='password123')
        response = self.client.post(reverse('shows:add_play'), {
            'title': 'New Play',
            'genre': 'theatre',
            'description': '',
            'contributors-TOTAL_FORMS': '0',
            'contributors-INITIAL_FORMS': '0',
            'contributors-MIN_NUM_FORMS': '0',
            'contributors-MAX_NUM_FORMS': '1000',
        })
        self.assertTrue(mock_delay.called)

    @patch('core.tasks.moderate_play.delay')
    def test_edit_play_triggers_moderation_on_title_change(self, mock_delay):
        play = self._make_published_play()
        self.client.login(email='owner@example.com', password='password123')
        self.client.post(reverse('shows:edit_play', args=[play.pk]), {
            'title': 'Updated Title',
            'genre': 'theatre',
            'description': '',
            'contributors-TOTAL_FORMS': '0',
            'contributors-INITIAL_FORMS': '0',
            'contributors-MIN_NUM_FORMS': '0',
            'contributors-MAX_NUM_FORMS': '1000',
        })
        self.assertTrue(mock_delay.called)
```

- [ ] **Step 2 : Lancer pour vérifier l'échec**

```bash
uv run python manage.py test shows.tests.PlayViewModerationTests
```

Expected: plusieurs FAIL

- [ ] **Step 3 : Modifier `play_detail` dans shows/views.py**

Remplacer la vue `play_detail` existante :

```python
def play_detail(request, pk):
    play = get_object_or_404(Play, pk=pk)

    if play.moderation_status != Play.PUBLISHED:
        if not request.user.is_authenticated or request.user != play.user:
            raise Http404

    representations = play.representations.order_by('datetime')
    troupe_profile = getattr(play.user, 'troupe_profile', None) if play.user else None
    accepted_members = (
        PlayMembership.objects
        .filter(play=play, status=PlayMembership.STATUS_ACCEPTED)
        .select_related('user', 'user__actor_profile', 'user__troupe_profile')
        .order_by('created_at')
    )
    user_membership = None
    if request.user.is_authenticated:
        user_membership = PlayMembership.objects.filter(play=play, email=request.user.email).first()
    return render(request, "shows/play_detail.html", {
        "play": play,
        "representations": representations,
        "troupe_profile": troupe_profile,
        "accepted_members": accepted_members,
        "user_membership": user_membership,
    })
```

Ajouter l'import manquant en haut de `shows/views.py` :

```python
from django.http import HttpResponseForbidden, HttpResponse, Http404
```

(Http404 est à ajouter à l'import existant qui a déjà HttpResponseForbidden et HttpResponse)

- [ ] **Step 4 : Modifier `add_play` dans shows/views.py**

Ajouter l'import de la tâche en haut du fichier (avec les autres imports) :

```python
from core.tasks import moderate_play
```

Dans `add_play`, après `_save_play_extra_photos(play, ...)` et avant `return redirect(...)` :

```python
            moderate_play.delay(play.pk)
            return redirect("shows:play_detail", pk=play.pk)
```

(Remplace le `return redirect` existant)

- [ ] **Step 5 : Modifier `edit_play` dans shows/views.py**

Dans `edit_play`, avant le bloc `if form.is_valid()`, capturer les valeurs actuelles :

```python
    if request.method == "POST":
        # Capture before save for moderation diff
        old_title = play.title
        old_desc = play.description
        old_poster_name = play.poster.name if play.poster else None
        old_cover_name = play.cover_image.name if play.cover_image else None

        form = PlayForm(request.POST, request.FILES, instance=play)
        formset = ContributorFormSet(request.POST, prefix="contributors", instance=play)

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                play = form.save(commit=False)
                if request.POST.get("poster-clear") == "on" and play.poster:
                    play.poster.delete(save=False)
                    play.poster = None
                if request.POST.get("cover-clear") == "on" and play.cover_image:
                    play.cover_image.delete(save=False)
                    play.cover_image = None
                play.save()
                formset.instance = play
                formset.save()

            _delete_play_extra_photos(play, request.POST)
            _save_play_extra_photos(play, request.FILES.getlist('extra_photos'))
            _process_invitations(request, play)
            _update_membership_roles(request, play)

            # Re-modérer si champs modérés ont changé
            moderated_changed = (
                play.title != old_title
                or play.description != old_desc
                or (play.poster.name if play.poster else None) != old_poster_name
                or (play.cover_image.name if play.cover_image else None) != old_cover_name
                or 'poster' in request.FILES
                or 'cover_image' in request.FILES
                or request.POST.get("poster-clear") == "on"
                or request.POST.get("cover-clear") == "on"
            )
            if moderated_changed:
                play.moderation_status = Play.PENDING
                play.save(update_fields=['moderation_status'])
                moderate_play.delay(play.pk)

            return redirect("shows:play_detail", pk=play.pk)
```

- [ ] **Step 6 : Vérifier que les tests passent**

```bash
uv run python manage.py test shows.tests.PlayViewModerationTests
```

Expected: OK (7 tests)

- [ ] **Step 7 : Lancer la suite complète**

```bash
uv run python manage.py test
```

Expected: OK (tous les tests)

- [ ] **Step 8 : Commit**

```bash
git add shows/views.py shows/tests.py
git commit -m "feat: trigger moderate_play in views, restrict public access"
```

---

## Task 5 : Mettre à jour l'admin shows

**Files:**
- Modify: `shows/admin.py`

Pas de tests unitaires pour l'admin — la vérification se fait manuellement en navigant sur `/admin/shows/play/`.

- [ ] **Step 1 : Mettre à jour shows/admin.py**

```python
from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from moderation.models import ModerationResult
from .models import Play, PlayMembership, Representation, Contributor, PublicationCredit, Transaction


class ModerationResultInline(admin.TabularInline):
    model = ModerationResult
    fk_name = None  # pas de FK directe — on passe par Play.moderation
    # On utilise un readonly inline custom via show_change_link
    # À la place : on affiche les infos via readonly_fields sur PlayAdmin
    extra = 0
    can_delete = False


class ContributorInline(admin.TabularInline):
    model = Contributor
    extra = 1
    fields = ("role", "name")
    verbose_name = "Contributeur"
    verbose_name_plural = "Contributeurs"


class RepresentationInline(admin.TabularInline):
    model = Representation
    extra = 1
    fields = ("datetime", "venue", "city", "ticket_url")
    ordering = ("datetime",)
    verbose_name = "Représentation"
    verbose_name_plural = "Représentations"


@admin.register(Play)
class PlayAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "genre", "moderation_status", "user", "created_at")
    list_editable = ("moderation_status",)
    search_fields = ("title", "company", "author")
    list_filter = ("moderation_status", "genre", "year_created")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "moderation_preview")
    inlines = [ContributorInline, RepresentationInline]

    fieldsets = (
        (_("Contenu"), {
            "fields": ("title", "author", "company", "genre", "description", "duration", "year_created", "website"),
        }),
        (_("Médias"), {
            "fields": ("poster", "cover_image"),
        }),
        (_("Modération"), {
            "fields": ("moderation_status", "moderation", "moderation_preview"),
        }),
        (_("Métadonnées"), {
            "fields": ("user", "created_at"),
        }),
    )

    actions = ("valider_pieces", "rejeter_pieces")

    @admin.display(description=_("Résumé modération"))
    def moderation_preview(self, obj):
        if not obj.moderation:
            return "—"
        parts = []
        if obj.moderation.reasons:
            parts.append(f"Texte : {obj.moderation.reasons}")
        if obj.moderation.image_reasons:
            parts.append(f"Images : {obj.moderation.image_reasons}")
        return " | ".join(parts) if parts else "✅ Aucun problème détecté"

    @admin.action(description=_("Valider les pièces sélectionnées"))
    def valider_pieces(self, request, queryset):
        updated = queryset.update(moderation_status='published')
        self.message_user(request, _("%d pièce(s) validée(s).") % updated, level=messages.SUCCESS)

    @admin.action(description=_("Rejeter les pièces sélectionnées"))
    def rejeter_pieces(self, request, queryset):
        updated = queryset.update(moderation_status='rejected')
        self.message_user(request, _("%d pièce(s) rejetée(s).") % updated, level=messages.WARNING)


@admin.register(Representation)
class RepresentationAdmin(admin.ModelAdmin):
    list_display = ("play", "datetime", "venue", "city")
    list_filter = ("city",)
    search_fields = ("play__title", "venue", "city")
    ordering = ("-datetime",)


@admin.register(PublicationCredit)
class PublicationCreditAdmin(admin.ModelAdmin):
    list_display = ("user", "remaining_credits")
    search_fields = ("user__username",)


@admin.register(PlayMembership)
class PlayMembershipAdmin(admin.ModelAdmin):
    list_display = ('play', 'email', 'direction', 'status', 'role', 'initiated_by', 'created_at')
    list_filter = ('direction', 'status')
    search_fields = ('email', 'play__title')
    ordering = ('-created_at',)
    readonly_fields = ('token',)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("user", "credits_purchased", "amount", "date")
    list_filter = ("date",)
    search_fields = ("user__username",)
    ordering = ("-date",)
```

- [ ] **Step 2 : Vérifier qu'il n'y a pas d'erreur de démarrage**

```bash
uv run python manage.py check
```

Expected: System check identified no issues.

- [ ] **Step 3 : Commit**

```bash
git add shows/admin.py
git commit -m "feat: update PlayAdmin with moderation_status filter and actions"
```

---

## Task 6 : Bandeau modération dans play_detail.html

**Files:**
- Modify: `shows/templates/shows/play_detail.html`

- [ ] **Step 1 : Localiser la zone propriétaire dans play_detail.html**

Ouvrir `shows/templates/shows/play_detail.html` et chercher le bloc où sont affichés les boutons "Modifier" / "Supprimer" (réservés au propriétaire). C'est la zone à augmenter.

Chercher :
```bash
grep -n "edit_play\|delete_play\|play.user\|request.user" shows/templates/shows/play_detail.html
```

- [ ] **Step 2 : Ajouter le bandeau de statut avant les boutons d'action**

Dans la section propriétaire (`{% if request.user == play.user %}`), ajouter le bandeau juste avant les boutons :

```html
{% if request.user == play.user %}
<div class="border-t border-ink/8 pt-8 space-y-4">

    {% if play.moderation_status == 'pending' %}
    <div class="border-l-4 border-amber-400 bg-ink/3 px-4 py-3">
        <p class="text-sm text-ink-soft">
            <i class="fa-solid fa-circle-notch fa-spin text-amber-500 mr-1.5"></i>
            Votre pièce est en cours de vérification automatique — elle sera visible dans quelques instants.
        </p>
    </div>
    {% elif play.moderation_status == 'under_review' %}
    <div class="border-l-4 border-amber-400 bg-ink/3 px-4 py-3">
        <p class="text-sm text-ink-soft">
            <i class="fa-solid fa-circle-exclamation text-amber-500 mr-1.5"></i>
            Votre pièce est examinée par notre équipe — elle n'est pas visible publiquement. Vous serez notifié par email dès qu'elle sera traitée.
        </p>
    </div>
    {% elif play.moderation_status == 'rejected' %}
    <div class="border-l-4 border-red-400 bg-red-50 px-4 py-3">
        <p class="text-sm font-bold text-red-700 mb-1">Pièce non publiée</p>
        {% if play.moderation and play.moderation.get_localized_reasons %}
        <ul class="text-sm text-red-600 space-y-0.5">
            {% for reason in play.moderation.get_localized_reasons %}
            <li class="flex items-start gap-1.5"><span class="mt-0.5 shrink-0">–</span> {{ reason }}</li>
            {% endfor %}
        </ul>
        {% endif %}
    </div>
    {% else %}
    <div class="border-l-4 border-ink/15 bg-ink/3 px-4 py-3">
        <p class="text-sm text-ink-soft">
            <i class="fa-solid fa-circle-check text-green-500 mr-1.5"></i>
            Votre pièce est en ligne.
        </p>
    </div>
    {% endif %}

    <div class="flex flex-wrap gap-2">
        <a href="{% url 'shows:edit_play' pk=play.pk %}"
           class="flex items-center gap-2 px-4 py-2
                  text-[11px] font-bold uppercase tracking-[0.12em]
                  border border-ink/20 text-ink-soft hover:border-ink hover:text-ink transition-colors">
            <i class="fa-solid fa-pen text-[10px]"></i>Modifier
        </a>
        <a href="{% url 'shows:delete_play' pk=play.pk %}"
           class="flex items-center gap-2 px-4 py-2
                  text-[11px] font-bold uppercase tracking-[0.12em]
                  text-red-400 hover:text-red-600 hover:bg-red-50
                  border border-transparent hover:border-red-200 transition-colors ml-auto">
            <i class="fa-solid fa-trash text-[10px]"></i>Supprimer
        </a>
    </div>

</div>
{% endif %}
```

**Note :** remplacer le bloc `{% if request.user == play.user %}` existant par ce nouveau bloc complet (qui inclut déjà les boutons Modifier/Supprimer). Ne pas dupliquer les boutons.

- [ ] **Step 3 : Vérifier visuellement**

```bash
uv run python manage.py runserver
```

- Créer une pièce → vérifier que le bandeau "En cours de vérification" apparaît
- Aller dans l'admin → valider la pièce → rafraîchir → "Votre pièce est en ligne"
- Aller dans l'admin → rejeter → bandeau rouge avec raisons si présentes

- [ ] **Step 4 : Lancer la suite complète des tests**

```bash
uv run python manage.py test
```

Expected: OK

- [ ] **Step 5 : Commit**

```bash
git add shows/templates/shows/play_detail.html
git commit -m "feat: add moderation status banner to play_detail for owner"
```

---

## Vérification finale

- [ ] Créer une pièce → statut `pending` dans l'admin ✓
- [ ] La tâche Celery la publie → statut `published` ✓
- [ ] Pièce `pending` non accessible aux non-propriétaires (404) ✓
- [ ] Admin : filtrer par `moderation_status`, valider/rejeter en masse ✓
- [ ] `uv run python manage.py test` → tous les tests passent ✓
