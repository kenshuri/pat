# Notification enrichie pour le flag automatique de messages

**Date** : 2026-06-07
**Statut** : validé

## Contexte

Quand un message de la messagerie interne matche une regex suspecte
(`messaging/moderation.py`), `_apply_moderation()` le flagge et envoie aux
admins un email brut via `mail_admins()` : sujet préfixé `[Django]`, corps de
deux lignes, aucune raison précise, aucun lien d'action. Le signalement
*manuel* (`report_message`), lui, envoie un email HTML riche
(`templates/emails/report_notification.html`) avec la conversation complète et
des liens admin.

Objectif : aligner le flag automatique sur le circuit du signalement manuel,
avec en plus la **raison précise** de la détection (quel pattern, quel
extrait), pour trier les faux positifs en quelques secondes.

Note : la détection messagerie est 100 % regex — Mistral AI n'intervient que
sur la modération des annonces (`moderation.services.moderate_text`). Extraire
l'extrait matché est donc trivial via `re.search()`.

## Design

### 1. `messaging/moderation.py` — raison précise

Nouvelle fonction publique :

```python
def get_flag_reason(text: str) -> tuple[str, str] | None:
    """Retourne (label, extrait) si le texte est suspect, sinon None."""
```

- `("Motif financier", "<extrait matché>")` si `_FINANCIAL_PATTERNS` matche
- `("Lien externe", "<URL matchée>")` si `_LINK_PATTERN` matche — la regex
  lien est étendue pour capturer l'URL complète (`https?://\S+`) et non
  juste le préfixe
- L'ordre de priorité : financier d'abord (plus grave), lien ensuite
- Les fonctions `check_financial_patterns` / `check_external_links`
  existantes sont conservées (rétrocompatibilité)

### 2. `_apply_moderation` — flag seul, plus d'envoi d'email

```python
def _apply_moderation(msg, body):
    reason = get_flag_reason(body)
    if reason:
        label, snippet = reason
        msg.is_flagged = True
        msg.flag_reason = f'Détection automatique — {label} : {snippet}'
    return bool(reason)
```

- Plus de `mail_admins()` ici : l'email part après `msg.save()` pour que le
  lien admin vers le message (pk) fonctionne
- Le paramètre `sender` (devenu inutile) est retiré
- `flag_reason` précis → visible aussi dans l'admin Django

### 3. `_send_report_notification(request, msg, reason, auto=False)`

En mode `auto=True` :

- **Sujet** : `[PAT] 🤖 Détection auto — {label} — {titre annonce}`
  (label court, pas l'extrait complet)
- **Template** : même fichier `report_notification.html`, nouvelle variable
  de contexte `is_auto` :
  - Header : « 🤖 Message signalé automatiquement » (au lieu de
    « 🚩 Message signalé »)
  - Ligne « Signalé par » → « Détection automatique » (pas de
    reporter_name/email)
  - Bouton « Profil signalant » masqué
  - Reste identique : raison (avec extrait), annonce, conversation complète
    avec message surligné, boutons annonce / profil expéditeur / admin Django
- Le corps texte (fallback) reflète les mêmes infos

En mode manuel (défaut) : comportement strictement inchangé.

### 4. Points d'appel (`conversation_detail` et `new_conversation`)

```python
flagged = _apply_moderation(msg, body)
msg.save()
conv.save()
if flagged:
    _send_report_notification(request, msg, msg.flag_reason, auto=True)
```

- Envoi non bloquant : le `try/except` + `logger.error` existant de
  `_send_report_notification` est conservé — si l'email échoue, le message
  utilisateur part quand même
- Le message flaggé reste **délivré** au destinataire (flag ≠ blocage)

### 5. Tests — `messaging/tests.py` (nouveau fichier)

- Unitaires `get_flag_reason` : lien http/https (extrait = URL complète),
  motif financier (iban, virement…), texte sain → `None`, priorité
  financier > lien
- Intégration : envoi d'un message contenant un lien via la vue →
  `mail.outbox` contient un email avec sujet `🤖 Détection auto`,
  `flag_reason` du message contient l'extrait, message bien créé en base

## Hors périmètre

- Affinage des règles de détection (whitelist Instagram/YouTube, etc.) —
  à discuter séparément
- Le circuit Mistral des annonces
- Le mail de signalement manuel (comportement inchangé)
