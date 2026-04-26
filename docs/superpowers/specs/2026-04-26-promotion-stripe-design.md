# Promotion Stripe — Design

**Date :** 2026-04-26
**Statut :** Approuvé
**Dépendance :** Spec modération des pièces (2026-04-26-moderation-pieces-design.md) doit être implémentée en premier.

---

## Objectif

Permettre aux utilisateurs connectés de payer via Stripe pour afficher leur pièce dans le bandeau promotionnel de la page d'accueil, sur une période réservée à l'avance. Un seul bandeau actif à la fois, pas de chevauchement.

## Tarifs

| Formule | Durée | Prix |
|---------|-------|------|
| `day` | 1 jour | 3 € |
| `week` | 7 jours | 10 € |
| `month` | 30 jours | 30 € |

## Modèle de données

### Évolution de `Promote`

Ajout des champs suivants au modèle existant :

```python
class Promote(models.Model):
    # --- existant ---
    user        = ForeignKey(CustomUser, on_delete=CASCADE)
    title       = CharField(max_length=120)
    slug        = SlugField(unique=True, blank=True)
    start_date  = DateField()
    end_date    = DateField()
    price_paid  = DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    impression_count    = PositiveIntegerField(default=0)
    click_count         = PositiveIntegerField(default=0)
    detail_view_count   = PositiveIntegerField(default=0)
    booking_click_count = PositiveIntegerField(default=0)
    created_at  = DateTimeField(auto_now_add=True)
    updated_at  = DateTimeField(auto_now=True)

    # --- nouveaux ---
    play              = ForeignKey('shows.Play', null=True, blank=True, on_delete=SET_NULL, related_name='promotions')
    stripe_session_id = CharField(max_length=255, blank=True, default='')
    formula           = CharField(max_length=10, choices=[('day','Jour'),('week','Semaine'),('month','Mois')], blank=True, default='')
    status            = CharField(max_length=20, choices=[
                            ('pending_payment', 'En attente de paiement'),
                            ('confirmed', 'Confirmé'),
                            ('expired', 'Expiré'),
                        ], default='pending_payment')
```

`slug` est auto-généré à partir du titre de la pièce + date de début (ex. `romeo-et-juliette-2026-05-10`).

## URLs

Préfixe `promote/` (cohérent avec les URLs existantes de l'app `promote`).

```
GET  /promote/sponsor/                          → liste des pièces publiées de l'utilisateur
GET  /promote/sponsor/calendar/                → page avec calendrier + formulaire de réservation
GET  /promote/sponsor/availability/            → JSON des périodes confirmées (pour le calendrier)
GET  /promote/sponsor/checkout/<play_id>/      → création session Stripe + redirect
GET  /promote/sponsor/confirmation/<session_id>/ → page de confirmation post-paiement
GET  /promote/sponsor/cancel/                  → page d'annulation (abandon Stripe)
POST /promote/sponsor/webhook/                 → endpoint webhook Stripe
```

Toutes les vues sauf le webhook requièrent `@login_required`. Le webhook est exempt de CSRF.

## Point d'entrée depuis la page pièce

Sur `shows/templates/shows/play_detail.html`, dans la zone propriétaire (visible uniquement si `request.user == play.user`) : bouton **"Promouvoir cette pièce"** liant vers `/promote/sponsor/?play=<pk>`. Si la pièce n'est pas `published`, le bouton est désactivé avec un tooltip "Votre pièce doit être validée avant de pouvoir être promue."

## Flux utilisateur

1. `/promouvoir/` : liste les pièces `published` de l'utilisateur. Si aucune pièce n'est publiée, message explicatif.
2. Clic sur une pièce → `/promouvoir/calendrier/` avec la pièce pré-sélectionnée, calendrier des disponibilités, choix de formule et date de début.
3. Validation du formulaire → vérification côté serveur qu'il n'y a pas de chevauchement → création d'un `Promote` en `pending_payment` → redirect vers Stripe Checkout.
4. Stripe Checkout → paiement → redirect vers `/promouvoir/confirmation/<session_id>/`.
5. Abandon → redirect vers `/promouvoir/annulation/`.

**Note sur la concurrence :** le slot n'est pas réservé pendant le checkout (pas de réservation sans paiement confirmé). En cas de conflit (deux paiements simultanés sur la même période), le premier webhook reçu confirme, le second reçoit une erreur gérée silencieusement (le `Promote` reste `pending_payment` et expire).

## Calendrier des disponibilités

Endpoint `GET /promouvoir/disponibilites/` retourne :

```json
{
  "booked": [
    {"start": "2026-05-01", "end": "2026-05-07"},
    {"start": "2026-05-15", "end": "2026-05-15"}
  ]
}
```

Côté frontend : Flatpickr en mode `range` avec `disable` sur les dates déjà réservées. La date de fin est calculée automatiquement selon la formule choisie.

## Session Stripe Checkout

Paramètres de la session :

```python
stripe.checkout.Session.create(
    payment_method_types=['card'],
    line_items=[{
        'price_data': {
            'currency': 'eur',
            'unit_amount': <prix_en_centimes>,
            'product_data': {'name': f"Bandeau — {play.title} ({formule_label})"},
        },
        'quantity': 1,
    }],
    mode='payment',
    success_url=f"{SITE_URL}/promouvoir/confirmation/{{CHECKOUT_SESSION_ID}}/",
    cancel_url=f"{SITE_URL}/promouvoir/annulation/",
    metadata={
        'promote_id': str(promote.pk),
    },
    customer_email=request.user.email,
)
```

L'ID de session est stocké dans `Promote.stripe_session_id` avant la redirection.

## Webhook Stripe

Endpoint `POST /promouvoir/stripe/webhook/` :

1. Vérifie la signature avec `stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)`
2. Filtre l'événement `checkout.session.completed`
3. Récupère `promote_id` depuis `session.metadata`
4. Met à jour `Promote` : `status='confirmed'`, `price_paid=session.amount_total/100`
5. Vérification d'unicité : si une autre promotion `confirmed` chevauche déjà la période, log l'anomalie sans crasher
6. Retourne HTTP 200 dans tous les cas (Stripe re-essaie en cas d'erreur)

Variable d'environnement requise : `STRIPE_WEBHOOK_SECRET`, `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`.

## Page de confirmation

`GET /promouvoir/confirmation/<session_id>/` :
- Récupère le `Promote` via `stripe_session_id`
- Vérifie que `request.user == promote.user`
- Affiche : pièce mise en avant, période (du X au Y), formule, montant payé
- Lien vers la page d'accueil pour voir le bandeau si la période est en cours

## Bandeau générique

Template `promote/templates/promote/banner_play.html` — remplace les templates codés à la main pour les promotions self-service :

```html
<!-- poster | titre + compagnie + prochaine représentation | bouton En savoir plus -->
```

La logique de sélection dans `core/views.index` :
1. Cherche un `Promote` avec `status='confirmed'`, `start_date <= today <= end_date`, trié par `start_date` (le plus récent en premier en cas de bug de chevauchement)
2. Si `promo.play` existe → `include 'promote/banner_play.html'`
3. Sinon → ancien système de slug (rétrocompatibilité pour les bandeaux manuels)

## Admin

- `list_display` : `title`, `play`, `status`, `formula`, `start_date`, `end_date`, `price_paid`, `user`
- `list_filter` : `status`, `formula`, `start_date`
- Action : `marquer_expire` pour passer manuellement des promos en `expired`

## Fichiers à créer / modifier

| Fichier | Action |
|---------|--------|
| `promote/models.py` | Ajouter `play`, `stripe_session_id`, `formula`, `status` |
| `promote/migrations/XXXX_add_stripe_fields.py` | Migration |
| `promote/views.py` | Vues : liste, calendrier, disponibilites, checkout, confirmation, annulation, webhook |
| `promote/urls.py` | Nouvelles URLs |
| `promote/templates/promote/list.html` | Page liste des pièces |
| `promote/templates/promote/calendar.html` | Page calendrier + formulaire |
| `promote/templates/promote/confirmation.html` | Page confirmation post-paiement |
| `promote/templates/promote/annulation.html` | Page annulation |
| `promote/templates/promote/banner_play.html` | Bandeau générique |
| `promote/admin.py` | Mise à jour admin |
| `core/views.py` | Logique de sélection du bandeau mise à jour |
| `config/settings.py` | Variables Stripe |
| `requirements` / `pyproject.toml` | Ajouter `stripe` |
