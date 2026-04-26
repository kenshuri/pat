# Modération des pièces — Design

**Date :** 2026-04-26
**Statut :** Approuvé

---

## Objectif

Appliquer le même pipeline de modération automatique (Mistral texte + NudeNet images) aux pièces (`Play`) qu'aux offres (`Offer`). Une pièce validée (`published`) devient un "actif de confiance" pouvant être promu via Stripe sans re-modération.

## Architecture

Même pattern que la modération des offres, adapté au modèle `Play` :

- Champ `moderation_status` sur `Play` (CharField, mêmes choix que `Offer` : `pending` / `published` / `under_review` / `rejected`, défaut `pending`)
- FK `moderation = ForeignKey(ModerationResult, null=True, blank=True)` sur `Play`
- Tâche Celery `moderate_play(play_id)` déclenchée à la création et à la modification (champs surveillés : `title`, `description`, `poster`)
- Résultat stocké dans un `ModerationResult` lié à la pièce

## Champs modérés

| Champ | Modération texte | Modération image |
|-------|-----------------|-----------------|
| `title` | ✓ (Mistral) | — |
| `description` | ✓ (Mistral) | — |
| `poster` | — | ✓ (NudeNet) |
| `cover_image` | — | ✓ (NudeNet) |

Les champs non-modérables (`representations`, `contributors`, `website`, `year_created`) ne déclenchent **pas** de re-modération.

## Déclenchement

- **Création** : `moderate_play.delay(play.id)` appelé dans la vue `play_create` après `play.save()`
- **Modification** : `moderate_play.delay(play.id)` uniquement si au moins un champ modéré a changé (comparaison avant/après dans la vue `play_update`)
- La pièce passe à `pending` à chaque déclenchement de modération

## Tâche Celery `moderate_play`

Même structure que `moderate_offer` :
1. Modération texte : `moderate_text(f"{play.title}\n{play.description}")`
2. Modération image : NudeNet sur `poster` et `cover_image` (si présents)
3. Mise à jour du `ModerationResult` avec résultats texte + image
4. Décision : `published` si tout OK, `under_review` sinon
5. `autoretry_for=(Exception,)`, `max_retries=3`, `retry_backoff=60`
6. Échec après tous les retries → `under_review`

## Accès public

- Pièces `under_review` et `rejected` : inaccessibles publiquement (404 pour les non-propriétaires)
- Pièces `pending` : inaccessibles publiquement, propriétaire voit un bandeau "En cours de vérification"
- Pièces `published` : accessibles normalement

## Admin

- `list_display` : ajouter `moderation_status`
- `list_filter` : filtrer par `moderation_status`
- Actions : `valider_pieces` (→ `published`), `rejeter_pieces` (→ `rejected`)
- Inline `ModerationResult` en lecture seule sur la fiche pièce

## Contrainte promotion

Seules les pièces avec `moderation_status == 'published'` peuvent être sélectionnées dans le flux de promotion Stripe (sous-projet B).

## Fichiers à créer / modifier

| Fichier | Action |
|---------|--------|
| `shows/models.py` | Ajouter `moderation_status`, `moderation` FK |
| `shows/migrations/XXXX_add_play_moderation.py` | Migration |
| `core/tasks.py` | Ajouter `moderate_play` |
| `shows/views.py` | Déclencher `moderate_play` à la création/modification |
| `shows/admin.py` | Ajouter filtres, actions, inline modération |
| `shows/templates/shows/play_detail.html` | Bandeau statut modération (propriétaire) |
