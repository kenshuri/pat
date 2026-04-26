# Modération unifiée (texte + images) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer la modération texte synchrone par une tâche Celery async qui combine modération texte (Mistral) + images (NudeNet), avec statut `moderation_status` sur `Offer`, blocage modification si sous examen, email admin si flag.

**Architecture:** Chaque soumission d'annonce sauvegarde l'offre en `under_review` et dispatch `moderate_offer.delay(offer_id)`. La tâche Celery appelle `moderate_text()` puis `moderate_images()`, puis décide `published` ou reste `under_review` + email admin.

**Tech Stack:** Celery 5.6, NudeNet 3.4+, Mistral API, Django 5.1, Scaleway S3

---

## Fichiers touchés

| Fichier | Action | Rôle |
|---|---|---|
| `pyproject.toml` | Modifier | Ajouter `nudenet>=3.4` |
| `core/models.py` | Modifier | Ajouter `moderation_status` sur `Offer` |
| `moderation/models.py` | Modifier | Ajouter `images_passed`, `image_reasons` sur `ModerationResult` |
| `core/migrations/XXXX_moderation_status.py` | Créer | Migration schema + data |
| `moderation/migrations/XXXX_image_fields.py` | Créer | Migration schema |
| `core/services/__init__.py` | Créer | Package vide |
| `core/services/image_moderation.py` | Créer | Service NudeNet |
| `core/tasks.py` | Modifier | Tâche `moderate_offer` |
| `core/views.py` | Modifier | Async modération + blocage modification |
| `core/admin.py` | Modifier | Renommage méthode + actions valider/rejeter |
| `templates/emails/moderation_flagged.html` | Créer | Email admin |
| `core/templates/core/offer.html` | Modifier | Bandeau `under_review` |

---

## Task 1 : Installer nudenet

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1 : Ajouter nudenet dans pyproject.toml**

Dans le bloc `dependencies`, après `"celery[redis]>=5.4",` :

```toml
"nudenet>=3.4",
```

- [ ] **Step 2 : Installer**

```bash
uv sync
```

Résultat attendu : nudenet apparaît dans `.venv/Lib/site-packages/`.

- [ ] **Step 3 : Vérifier**

```bash
uv run python -c "from nudenet import NudeDetector; print('ok')"
```

Résultat attendu : `ok` (le modèle n'est pas encore téléchargé, juste l'import).

- [ ] **Step 4 : Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add nudenet"
```

---

## Task 2 : Ajouter `moderation_status` sur `Offer`

**Files:**
- Modify: `core/models.py`
- Create: migration via `makemigrations`

- [ ] **Step 1 : Ajouter les constantes et le champ dans `core/models.py`**

Dans la classe `Offer`, après les constantes `GENDER_CHOICES` (ligne ~68), ajouter :

```python
PUBLISHED = 'published'
UNDER_REVIEW = 'under_review'
REJECTED = 'rejected'

MODERATION_STATUS_CHOICES = [
    (PUBLISHED, 'Publiée'),
    (UNDER_REVIEW, 'Sous examen'),
    (REJECTED, 'Rejetée'),
]
```

Puis dans les champs du modèle, après `filled = models.BooleanField(default=False)` :

```python
moderation_status = models.CharField(
    max_length=20,
    choices=MODERATION_STATUS_CHOICES,
    default=UNDER_REVIEW,
)
```

- [ ] **Step 2 : Générer la migration schema**

```bash
uv run python manage.py makemigrations core --name moderation_status
```

Résultat attendu : `core/migrations/XXXX_moderation_status.py` créé.

- [ ] **Step 3 : Ajouter la migration de données dans le fichier généré**

Ouvrir le fichier de migration généré et ajouter une `RunPython` pour migrer les données existantes. Remplacer le contenu de `operations` par :

```python
import django.db.models.deletion
from django.db import migrations, models


def migrate_moderation_status(apps, schema_editor):
    Offer = apps.get_model('core', 'Offer')
    # Annonces avec modération texte passée → published
    Offer.objects.filter(moderation__passed=True).update(moderation_status='published')
    # Annonces sans modération ou modération échouée → under_review (déjà le défaut)


class Migration(migrations.Migration):

    dependencies = [
        ('core', 'XXXX_previous_migration'),  # remplacer par la migration précédente réelle
    ]

    operations = [
        migrations.AddField(
            model_name='offer',
            name='moderation_status',
            field=models.CharField(
                choices=[('published', 'Publiée'), ('under_review', 'Sous examen'), ('rejected', 'Rejetée')],
                default='under_review',
                max_length=20,
            ),
        ),
        migrations.RunPython(migrate_moderation_status, migrations.RunPython.noop),
    ]
```

> **Important :** remplacer `XXXX_previous_migration` par le nom de la migration précédente réel dans le fichier généré (il est déjà correct dans le fichier généré par makemigrations — juste ajouter la `RunPython`).

- [ ] **Step 4 : Appliquer la migration**

```bash
uv run python manage.py migrate
```

Résultat attendu : migration appliquée sans erreur.

- [ ] **Step 5 : Vérifier**

```bash
uv run python manage.py shell -c "
from core.models import Offer
print('published:', Offer.objects.filter(moderation_status='published').count())
print('under_review:', Offer.objects.filter(moderation_status='under_review').count())
"
```

Résultat attendu : les annonces publiées ont `published`, les autres `under_review`.

- [ ] **Step 6 : Commit**

```bash
git add core/models.py core/migrations/
git commit -m "feat: add moderation_status field on Offer"
```

---

## Task 3 : Ajouter `images_passed` et `image_reasons` sur `ModerationResult`

**Files:**
- Modify: `moderation/models.py`
- Create: migration via `makemigrations`

- [ ] **Step 1 : Ajouter les champs dans `moderation/models.py`**

Dans la classe `ModerationResult`, après `reasons = models.TextField(blank=True, null=True)` :

```python
images_passed = models.BooleanField(null=True, blank=True)
image_reasons = models.CharField(max_length=255, blank=True, default='')
```

- [ ] **Step 2 : Générer et appliquer la migration**

```bash
uv run python manage.py makemigrations moderation --name image_moderation_fields
uv run python manage.py migrate
```

Résultat attendu : migration appliquée sans erreur.

- [ ] **Step 3 : Vérifier**

```bash
uv run python manage.py check
```

Résultat attendu : `System check identified no issues (0 silenced).`

- [ ] **Step 4 : Commit**

```bash
git add moderation/models.py moderation/migrations/
git commit -m "feat: add images_passed and image_reasons on ModerationResult"
```

---

## Task 4 : Créer le service `image_moderation`

**Files:**
- Create: `core/services/__init__.py`
- Create: `core/services/image_moderation.py`

- [ ] **Step 1 : Créer `core/services/__init__.py`** (fichier vide)

- [ ] **Step 2 : Créer `core/services/image_moderation.py`**

```python
import logging
import tempfile
import os
import requests
from nudenet import NudeDetector

logger = logging.getLogger(__name__)

UNSAFE_LABELS = {
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "FEMALE_BREAST_EXPOSED",
    "ANUS_EXPOSED",
    "BUTTOCKS_EXPOSED",
}
UNSAFE_THRESHOLD = 0.6

_detector = None


def _get_detector():
    global _detector
    if _detector is None:
        _detector = NudeDetector()
    return _detector


def _analyze_image_file(path: str) -> bool:
    """Retourne True si l'image est safe."""
    try:
        results = _get_detector().detect(path)
        for detection in results:
            if (
                detection.get("class") in UNSAFE_LABELS
                and detection.get("score", 0) >= UNSAFE_THRESHOLD
            ):
                return False
        return True
    except Exception as e:
        logger.error("NudeNet analyze error for %s: %s", path, e)
        return True  # fail open sur une image individuelle


def _download_to_temp(image_field) -> str | None:
    """Télécharge une ImageField S3 dans un fichier temporaire. Retourne le path ou None."""
    try:
        url = image_field.url
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        suffix = os.path.splitext(image_field.name)[-1] or ".webp"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
            f.write(response.content)
            return f.name
    except Exception as e:
        logger.error("Failed to download image %s: %s", image_field.name, e)
        return None


def moderate_images(offer) -> tuple[bool, str]:
    """
    Analyse cover_image + toutes les OfferPhoto d'une annonce.
    Retourne (passed: bool, reasons: str).
    passed=True si toutes les images sont safe.
    reasons liste les noms des images flagguées, séparés par des virgules.
    """
    flagged = []
    temp_files = []

    images_to_check = []

    if offer.cover_image:
        images_to_check.append(("cover_image", offer.cover_image))

    for photo in offer.photos.all():
        images_to_check.append((f"photo_{photo.pk}", photo.image))

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

- [ ] **Step 3 : Vérifier l'import**

```bash
uv run python manage.py shell -c "from core.services.image_moderation import moderate_images; print('ok')"
```

Résultat attendu : `ok`

- [ ] **Step 4 : Commit**

```bash
git add core/services/
git commit -m "feat: add image moderation service with NudeNet"
```

---

## Task 5 : Mettre à jour `core/tasks.py`

**Files:**
- Modify: `core/tasks.py`

- [ ] **Step 1 : Remplacer le contenu de `core/tasks.py`**

```python
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
        # fail closed : moderation_status reste under_review


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
    body = render_to_string('emails/moderation_flagged.html', {
        'offer': offer,
        'reasons': reasons,
        'admin_url': f"{settings.SITE_URL}/admin/core/offer/{offer.pk}/change/",
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
```

- [ ] **Step 2 : Vérifier l'import**

```bash
uv run python manage.py shell -c "from core.tasks import moderate_offer; print(moderate_offer)"
```

Résultat attendu : `<@task: core.tasks.moderate_offer of config at 0x...>`

- [ ] **Step 3 : Commit**

```bash
git add core/tasks.py
git commit -m "feat: add moderate_offer celery task"
```

---

## Task 6 : Mettre à jour les vues

**Files:**
- Modify: `core/views.py`

- [ ] **Step 1 : Mettre à jour les imports en haut de `core/views.py`**

Remplacer :
```python
from moderation.services import moderate_text
```
Par :
```python
from core.tasks import moderate_offer
```

- [ ] **Step 2 : Mettre à jour `add_offer` dans `core/views.py`**

Remplacer (autour de la ligne 162) :
```python
            offer.author = request.user
            moderation_result = moderate_text(offer.get_moderation_text())
            offer.moderation = moderation_result
            offer.save()
            _save_extra_photos(offer, request.FILES.getlist('extra_photos'))
            offer_id = offer.id
            return redirect('offer', offer_id=offer_id)
```

Par :
```python
            offer.author = request.user
            offer.moderation_status = Offer.UNDER_REVIEW
            offer.save()
            _save_extra_photos(offer, request.FILES.getlist('extra_photos'))
            moderate_offer.delay(offer.id)
            offer_id = offer.id
            return redirect('offer', offer_id=offer_id)
```

- [ ] **Step 3 : Mettre à jour `update_offer` dans `core/views.py`**

Dans la vue `update_offer`, ajouter le blocage AVANT le traitement du formulaire POST (juste après `offer = get_object_or_404(Offer, id=offer_id)`) :

```python
        if offer.moderation_status == Offer.UNDER_REVIEW:
            from django.contrib import messages as django_messages
            django_messages.error(request, "Votre annonce est en cours d'examen et ne peut pas être modifiée pour le moment.")
            return redirect('offer', offer_id=offer_id)
```

Puis remplacer la partie modération dans le bloc `if form.is_valid()` (autour de la ligne 185) :
```python
            # Avant
            moderation_result = moderate_text(offer.get_moderation_text())
            offer.moderation = moderation_result
            offer.save()
```
Par :
```python
            offer.moderation_status = Offer.UNDER_REVIEW
            offer.save()
            _save_extra_photos(offer, request.FILES.getlist('extra_photos'))
            moderate_offer.delay(offer.id)
            return redirect('offer', offer_id=offer_id)
```

> Note : supprimer aussi l'appel `_save_extra_photos` + `_delete_extra_photos` qui suivent dans le bloc original puisqu'on les a déplacés.

- [ ] **Step 4 : Mettre à jour `_build_offer_queryset` dans `core/views.py`**

Remplacer (ligne ~35) :
```python
    qs = Offer.objects.select_related('moderation').filter(filled=False).filter(
        Q(moderation__isnull=True) | Q(moderation__passed=True)
    )
```
Par :
```python
    qs = Offer.objects.filter(filled=False, moderation_status=Offer.PUBLISHED)
```

- [ ] **Step 5 : Vérifier**

```bash
uv run python manage.py check
```

Résultat attendu : `System check identified no issues (0 silenced).`

- [ ] **Step 6 : Commit**

```bash
git add core/views.py
git commit -m "feat: async moderation in views + block update if under_review"
```

---

## Task 7 : Mettre à jour l'admin

**Files:**
- Modify: `core/admin.py`

**Attention :** `core/admin.py` a déjà une méthode `moderation_status` (ligne 142) qui affiche `moderation.get_manual_status_display()`. Maintenant que `Offer` a un vrai champ `moderation_status`, il faut renommer cette méthode pour éviter le conflit.

- [ ] **Step 1 : Renommer la méthode `moderation_status` en `moderation_manual_status` dans `core/admin.py`**

Dans `list_display`, remplacer `"moderation_status"` par `"moderation_manual_status"` et `"moderation_status_field"`.

Remplacer la méthode (ligne ~141) :
```python
    @admin.display(description=_("Statut modération"))
    def moderation_status(self, obj):
        if obj.moderation_id and hasattr(obj.moderation, "get_manual_status_display"):
            return obj.moderation.get_manual_status_display()
        return "—"
```
Par :
```python
    @admin.display(description=_("Statut manuel"))
    def moderation_manual_status(self, obj):
        if obj.moderation_id and hasattr(obj.moderation, "get_manual_status_display"):
            return obj.moderation.get_manual_status_display()
        return "—"
```

- [ ] **Step 2 : Mettre à jour `list_display` dans `OfferAdmin`**

Remplacer :
```python
    list_display = (
        "id", "title", "section", "type", "category",
        "city", "gender", "age_range", "filled",
        "is_recent", "displayed_email", "contact_phone",
        "created_on", "author_display",
        "moderation_status", "moderation_passed",
    )
```
Par :
```python
    list_display = (
        "id", "title", "section", "type", "category",
        "city", "gender", "age_range", "filled",
        "is_recent", "displayed_email", "contact_phone",
        "created_on", "author_display",
        "moderation_status", "moderation_manual_status", "moderation_passed",
    )
```

- [ ] **Step 3 : Ajouter les actions valider/rejeter dans `OfferAdmin`**

Remplacer :
```python
    actions = ("marquer_comme_pourvue", "marquer_comme_ouverte")
```
Par :
```python
    actions = ("marquer_comme_pourvue", "marquer_comme_ouverte", "valider_annonces", "rejeter_annonces")
```

Puis ajouter les méthodes à la fin de la classe `OfferAdmin` :

```python
    @admin.action(description=_("Valider les annonces sélectionnées"))
    def valider_annonces(self, request, queryset):
        updated = queryset.update(moderation_status='published')
        self.message_user(
            request,
            _("%d annonce(s) validée(s) et publiée(s).") % updated,
            level=messages.SUCCESS,
        )

    @admin.action(description=_("Rejeter les annonces sélectionnées"))
    def rejeter_annonces(self, request, queryset):
        updated = queryset.update(moderation_status='rejected')
        self.message_user(
            request,
            _("%d annonce(s) rejetée(s).") % updated,
            level=messages.WARNING,
        )
```

- [ ] **Step 4 : Vérifier**

```bash
uv run python manage.py check
```

Résultat attendu : `System check identified no issues (0 silenced).`

- [ ] **Step 5 : Commit**

```bash
git add core/admin.py
git commit -m "feat: add moderation actions in admin + fix method naming conflict"
```

---

## Task 8 : Créer le template email admin

**Files:**
- Create: `templates/emails/moderation_flagged.html`

- [ ] **Step 1 : Créer `templates/emails/moderation_flagged.html`**

```html
<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f4f0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f4f0;padding:40px 16px;">
  <tr><td align="center">
    <table width="560" cellpadding="0" cellspacing="0" style="background:#fff;border:1px solid #e8e6e0;max-width:560px;width:100%;">

      <!-- Header -->
      <tr>
        <td style="background:#7B1C1C;padding:28px 32px;">
          <p style="margin:0;font-family:Georgia,serif;font-size:13px;font-weight:bold;letter-spacing:0.12em;text-transform:uppercase;color:rgba(255,255,255,0.8);">
            Petites Annonces Théâtre — Modération
          </p>
        </td>
      </tr>

      <!-- Body -->
      <tr>
        <td style="padding:32px;">
          <h1 style="margin:0 0 16px;font-size:18px;font-weight:bold;color:#7B1C1C;line-height:1.3;">
            Annonce #{{ offer.pk }} flagguée
          </h1>
          <p style="margin:0 0 8px;font-size:14px;color:#4a4640;">
            <strong>Titre :</strong> {{ offer.title }}
          </p>
          <p style="margin:0 0 8px;font-size:14px;color:#4a4640;">
            <strong>Auteur :</strong> {{ author_email }}
          </p>
          <p style="margin:0 0 20px;font-size:14px;color:#4a4640;">
            <strong>Raison(s) :</strong>
          </p>
          <ul style="margin:0 0 24px;padding-left:20px;">
            {% for reason in reasons %}
            <li style="font-size:14px;color:#4a4640;margin-bottom:4px;">{{ reason }}</li>
            {% endfor %}
          </ul>

          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="background:#7B1C1C;">
                <a href="{{ admin_url }}"
                   style="display:inline-block;padding:12px 24px;font-size:12px;font-weight:bold;letter-spacing:0.12em;text-transform:uppercase;color:#fff;text-decoration:none;">
                  Voir dans l'admin →
                </a>
              </td>
            </tr>
          </table>
        </td>
      </tr>

      <!-- Footer -->
      <tr>
        <td style="border-top:1px solid #f0ede8;padding:20px 32px;">
          <p style="margin:0;font-size:11px;color:#c0bdb8;line-height:1.6;">
            Email automatique — Petites Annonces Théâtre
          </p>
        </td>
      </tr>

    </table>
  </td></tr>
</table>
</body>
</html>
```

- [ ] **Step 2 : Commit**

```bash
git add templates/emails/moderation_flagged.html
git commit -m "feat: add moderation flagged email template"
```

---

## Task 9 : Mettre à jour le template `offer.html`

**Files:**
- Modify: `core/templates/core/offer.html`

- [ ] **Step 1 : Ajouter le bandeau `under_review` dans `offer.html`**

Au tout début du `{% block main %}` (juste après `{% block main %}`), ajouter :

```html
{% if offer.moderation_status == 'under_review' and request.user == offer.author %}
<div class="max-w-screen-xl mx-auto px-4 md:px-8 pt-6">
  <div class="rounded-xl border border-amber-300 bg-amber-50 px-6 py-4 text-amber-900">
    <p class="font-semibold text-sm mb-1">Annonce en cours de vérification</p>
    <p class="text-sm leading-relaxed">
      Votre annonce est examinée par notre équipe suite à une détection automatique.
      Elle n'est pas visible publiquement pour le moment.
      Vous serez notifié par email dès qu'elle sera traitée.
      Vous ne pouvez pas la modifier pendant cet examen.
    </p>
  </div>
</div>
{% endif %}
```

- [ ] **Step 2 : Vérifier que Django parse le template sans erreur**

```bash
uv run python manage.py shell -c "
from django.template.loader import get_template
t = get_template('core/offer.html')
print('ok')
"
```

Résultat attendu : `ok`

- [ ] **Step 3 : Commit**

```bash
git add core/templates/core/offer.html
git commit -m "feat: add under_review banner on offer page"
```

---

## Task 10 : Test end-to-end local

Cette tâche est manuelle — elle vérifie que tout fonctionne ensemble.

- [ ] **Step 1 : Démarrer l'infra**

```bash
# Terminal 1
docker compose up --build

# Terminal 2
uv run python manage.py runserver
```

- [ ] **Step 2 : Soumettre une annonce avec une image**

1. Se connecter sur http://127.0.0.1:8000
2. Créer une nouvelle annonce avec une image de couverture safe
3. Vérifier que la redirection vers la page annonce est **immédiate** (pas d'attente Mistral)
4. Vérifier que le bandeau "en cours de vérification" s'affiche
5. Attendre ~5s et rafraîchir — l'annonce doit être `published` et visible

- [ ] **Step 3 : Vérifier les logs du worker**

Dans le terminal Docker :
```
Task core.tasks.moderate_offer[...] succeeded
```

- [ ] **Step 4 : Vérifier l'admin**

Sur http://127.0.0.1:8000/admin/core/offer/ :
- La colonne `moderation_status` doit afficher `published` pour l'annonce créée
- Les actions "Valider" et "Rejeter" doivent être disponibles
