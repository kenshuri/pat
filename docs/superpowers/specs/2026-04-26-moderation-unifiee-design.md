# Modération unifiée (texte + images) — Design Spec

**Date :** 2026-04-26
**Scope :** Modération async des annonces (texte via Mistral + images via NudeNet), statut de modération sur Offer, blocage modification si sous examen, email admin, message utilisateur.

**Hors scope :** blocage de compte utilisateur (spec séparé), modération des shows (Phase B).

---

## Contexte

Aujourd'hui `moderate_text()` est appelé de façon synchrone dans les vues `add_offer` et `update_offer`. L'utilisateur attend la réponse de l'API Mistral avant d'être redirigé. Il n'y a pas de modération image. Un cas réel de contenu inapproprié a montré qu'une boucle modification rapide permettait de contourner la modération.

---

## Comportement cible

```
Utilisateur soumet annonce
        ↓
Offer sauvegardée avec statut "under_review"
Utilisateur redirigé immédiatement
        ↓
Tâche Celery : moderate_offer(offer_id)
        ↓
   moderate_text()  — API Mistral
   moderate_images() — NudeNet sur cover_image + toutes les OfferPhoto
        ↓
   Tout OK  → statut "published", annonce visible
   Un échec → statut reste "under_review" + email admin + message utilisateur
```

**Modification bloquée** tant que `moderation_status == 'under_review'`.

**Message utilisateur** affiché sur la page annonce si `under_review` :
> "Votre annonce est en cours de vérification par notre équipe. Vous serez notifié par email dès qu'elle sera traitée."

---

## Modèles

### `Offer` — ajout de `moderation_status`

```python
PUBLISHED = 'published'
UNDER_REVIEW = 'under_review'
REJECTED = 'rejected'

MODERATION_STATUS_CHOICES = [
    (PUBLISHED, 'Publiée'),
    (UNDER_REVIEW, 'Sous examen'),
    (REJECTED, 'Rejetée'),
]

moderation_status = models.CharField(
    max_length=20,
    choices=MODERATION_STATUS_CHOICES,
    default=UNDER_REVIEW,
)
```

Le champ `moderation` (FK vers `ModerationResult`) est conservé.

La logique de visibilité existante filtre déjà sur `moderation__passed`. On unifie : une annonce est visible si et seulement si `moderation_status == 'published'`.

### `ModerationResult` — ajout de deux champs image

```python
images_passed = models.BooleanField(null=True, blank=True)
# None = pas encore analysé, True = OK, False = contenu inapproprié

image_reasons = models.CharField(max_length=255, blank=True)
# ex: "cover_image" ou "photo_3,photo_7"
```

---

## Nouvelle dépendance

```
nudenet>=3.4
```

À ajouter dans `pyproject.toml`. NudeNet télécharge son modèle (~90 Mo) au premier appel et le met en cache dans `~/.NudeNet/`. Sur Railway, ce cache est recréé à chaque déploiement — acceptable.

---

## Service image moderation

**Fichier :** `core/services/image_moderation.py`

Responsabilité unique : analyser une liste d'images et retourner si elles sont safe.

```python
from nudenet import NudeDetector

UNSAFE_LABELS = {
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "FEMALE_BREAST_EXPOSED",
    "ANUS_EXPOSED",
    "BUTTOCKS_EXPOSED",
}
UNSAFE_THRESHOLD = 0.6  # score de confiance minimum pour flaguer

def moderate_images(offer) -> tuple[bool, str]:
    """
    Analyse toutes les images d'une annonce.
    Retourne (passed: bool, reasons: str).
    """
```

L'analyse se fait sur les fichiers téléchargés depuis S3 dans un répertoire temporaire (`tempfile`), puis supprimés après analyse.

---

## Tâche Celery

**Fichier :** `core/tasks.py`

```python
@shared_task
def moderate_offer(offer_id: int):
    offer = Offer.objects.select_related('moderation').get(pk=offer_id)

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
        _notify_admin_flagged(offer)

    offer.save()
```

En cas d'exception (API down, NudeNet crash) : `moderation_status` reste `under_review`, erreur loggée. Fail closed — l'annonce ne sera jamais publiée silencieusement en cas d'erreur.

---

## Vues modifiées

### `add_offer` et `update_offer`

Avant :
```python
moderation_result = moderate_text(offer.get_moderation_text())
offer.moderation = moderation_result
offer.save()
```

Après :
```python
offer.moderation_status = Offer.UNDER_REVIEW
offer.save()
moderate_offer.delay(offer.id)
```

### Blocage modification dans `update_offer`

```python
if offer.moderation_status == Offer.UNDER_REVIEW:
    messages.error(request, "Votre annonce est en cours d'examen et ne peut pas être modifiée.")
    return redirect('offer', offer_id=offer_id)
```

---

## Template `offer.html`

Bandeau affiché si `offer.moderation_status == 'under_review'` ET que l'utilisateur est l'auteur :

```html
<div class="alert alert-warning">
  Votre annonce est en cours de vérification par notre équipe.
  Vous serez notifié par email dès qu'elle sera traitée.
  Vous ne pouvez pas la modifier pendant cet examen.
</div>
```

---

## Email admin

**Template :** `templates/emails/moderation_flagged.html`

Contenu :
- Lien vers l'annonce dans l'admin Django
- Raison du flag (texte et/ou image)
- Nom/email de l'auteur

Envoyé à `ADMINS` (défini dans `settings.py`).

---

## Admin Django

Sur `OfferAdmin`, deux actions :
- **"Valider"** → `moderation_status = published`
- **"Rejeter"** → `moderation_status = rejected` + suppression de l'annonce

`moderation_status` affiché dans `list_display` pour visibilité rapide.

---

## Visibilité des annonces

Remplacer le filtre existant :
```python
# Avant
.filter(Q(moderation__isnull=True) | Q(moderation__passed=True))

# Après
.filter(moderation_status=Offer.PUBLISHED)
```

Plus simple et cohérent avec le nouveau système.

---

## Migration

1. Ajouter `moderation_status` sur `Offer` avec `default=UNDER_REVIEW`
2. Migration de données : toutes les annonces existantes avec `moderation__passed=True` → `PUBLISHED`, les autres → `UNDER_REVIEW`
3. Ajouter `images_passed` et `image_reasons` sur `ModerationResult`

---

## Ce qui n'est PAS dans ce scope

- Blocage de compte utilisateur
- Modération des shows
- Interface de modération dédiée (l'admin Django suffit)
- Notification email à l'utilisateur (seulement à l'admin pour l'instant)
