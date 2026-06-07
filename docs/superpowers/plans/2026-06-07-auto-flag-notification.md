# Notification enrichie pour le flag automatique — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer l'email brut `mail_admins()` du flag automatique de messages par l'email HTML riche du signalement manuel, avec la raison précise de la détection (pattern + extrait matché).

**Architecture:** `messaging/moderation.py` gagne `get_flag_reason()` qui retourne `(label, extrait)` au lieu d'un booléen. `_apply_moderation()` ne fait plus que poser `is_flagged`/`flag_reason` (raison précise) et retourne le tuple. L'email part **après** `msg.save()` via `_send_report_notification()` généralisé avec un paramètre `auto_label` (le label court sert au sujet — pas de parsing fragile de `flag_reason`). Le template `report_notification.html` gagne une variable `is_auto`.

**Tech Stack:** Django 5.1, regex stdlib, `django.core.mail` (locmem backend en test), templates Django.

**Spec:** `docs/superpowers/specs/2026-06-07-auto-flag-notification-design.md`

**Note d'écart vs spec:** la spec section 3 proposait `auto=False` ; on utilise `auto_label=None` (le mode auto = `auto_label is not None`) car le sujet de l'email a besoin du label court (« Lien externe ») et le parser depuis la chaîne `flag_reason` serait fragile. Même intention, signature plus propre.

**Commandes** (toujours via `uv run`, voir CLAUDE.md / préférences utilisateur) :
```bash
uv run python manage.py test messaging -v 2
```

## File Structure

- Modify: `messaging/moderation.py` — ajout `get_flag_reason()`, regex lien étendue à `https?://\S+`
- Modify: `messaging/views.py` — `_apply_moderation()`, `_send_report_notification()`, 2 points d'appel, imports
- Modify: `templates/emails/report_notification.html` — conditionnels `is_auto`
- Create: `messaging/tests.py` — tests unitaires + intégration

---

### Task 1: `get_flag_reason()` dans `messaging/moderation.py`

**Files:**
- Create: `messaging/tests.py`
- Modify: `messaging/moderation.py`

- [ ] **Step 1: Write the failing tests**

Créer `messaging/tests.py` :

```python
from django.test import TestCase

from .moderation import check_external_links, check_financial_patterns, get_flag_reason


class GetFlagReasonTests(TestCase):
    def test_external_link_returns_full_url(self):
        reason = get_flag_reason(
            'Mon portfolio : https://www.instagram.com/lucasfontayne/ merci !'
        )
        self.assertEqual(reason, ('Lien externe', 'https://www.instagram.com/lucasfontayne/'))

    def test_http_link_detected(self):
        label, snippet = get_flag_reason('voir http://example.com/page svp')
        self.assertEqual(label, 'Lien externe')
        self.assertEqual(snippet, 'http://example.com/page')

    def test_financial_keyword(self):
        label, snippet = get_flag_reason('envoyez-moi un virement rapidement')
        self.assertEqual(label, 'Motif financier')
        self.assertEqual(snippet.lower(), 'virement')

    def test_iban_like_sequence(self):
        label, snippet = get_flag_reason('mon compte : FR76 3000 1007 9412 3456 7890 185')
        self.assertEqual(label, 'Motif financier')
        self.assertIn('FR76', snippet)

    def test_clean_text_returns_none(self):
        self.assertIsNone(get_flag_reason(
            'Bonjour, je suis comédien et disponible pour une audition à Paris.'
        ))

    def test_financial_takes_priority_over_link(self):
        label, _ = get_flag_reason('paiement par virement, détails sur https://example.com')
        self.assertEqual(label, 'Motif financier')

    def test_legacy_checks_still_work(self):
        self.assertTrue(check_external_links('https://example.com'))
        self.assertTrue(check_financial_patterns('IBAN'))
        self.assertFalse(check_external_links('bonjour'))
        self.assertFalse(check_financial_patterns('bonjour'))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python manage.py test messaging -v 2`
Expected: `ImportError: cannot import name 'get_flag_reason'`

- [ ] **Step 3: Implement `get_flag_reason()`**

Remplacer le contenu de `messaging/moderation.py` par :

```python
import re

_FINANCIAL_PATTERNS = re.compile(
    r'\b(iban|bic|swift|virement|western\s*union|moneygram|paypal\.me|'
    r'[a-z]{2}\d{2}[\s\d]{10,30}|'  # IBAN-like sequences
    r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b)',  # card-like numbers
    re.IGNORECASE,
)

_LINK_PATTERN = re.compile(r'https?://\S+', re.IGNORECASE)


def check_financial_patterns(text: str) -> bool:
    return bool(_FINANCIAL_PATTERNS.search(text))


def check_external_links(text: str) -> bool:
    return bool(_LINK_PATTERN.search(text))


def get_flag_reason(text):
    """Retourne (label, extrait matché) si le texte est suspect, sinon None.

    Le motif financier est testé en premier (plus grave qu'un simple lien).
    """
    match = _FINANCIAL_PATTERNS.search(text)
    if match:
        return ('Motif financier', match.group(0))
    match = _LINK_PATTERN.search(text)
    if match:
        return ('Lien externe', match.group(0))
    return None
```

Seul changement aux regex existantes : `_LINK_PATTERN` passe de `https?://` à `https?://\S+` pour capturer l'URL complète (comportement de `check_external_links` inchangé pour toute URL réelle).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python manage.py test messaging -v 2`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add messaging/moderation.py messaging/tests.py
git commit -m "feat(messaging): get_flag_reason retourne le pattern et l'extrait matché"
```

---

### Task 2: Refactor `views.py` — flag précis + email riche après save

**Files:**
- Modify: `messaging/views.py` (imports ~l.5 et l.16, `_send_report_notification` l.49-98, `_apply_moderation` l.161-173, `conversation_detail` l.228-237, `new_conversation` l.274-284)
- Modify: `messaging/tests.py` (ajout tests d'intégration)

- [ ] **Step 1: Write the failing integration tests**

Ajouter à `messaging/tests.py` (imports en tête de fichier + nouvelle classe) :

```python
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse

from core.models import Offer
from .models import Conversation, Message
```

```python
class AutoFlagNotificationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(email='alice@example.com', password='pass12345')
        self.bob = User.objects.create_user(email='bob@example.com', password='pass12345')
        self.offer = Offer.objects.create(title='Casting Tartuffe', summary='Résumé', author=self.bob)
        self.conv = Conversation.objects.create(offer=self.offer, offer_title=self.offer.title)
        self.conv.participants.add(self.alice, self.bob)
        self.client.force_login(self.alice)

    def _admin_mails(self):
        return [m for m in mail.outbox if 'Détection auto' in m.subject]

    def test_message_with_link_flags_and_notifies_admins(self):
        self.client.post(
            reverse('messaging:conversation', args=[self.conv.pk]),
            {'body': 'Mon portfolio : https://www.instagram.com/lucasfontayne/'},
        )
        msg = Message.objects.get(conversation=self.conv, sender=self.alice)
        self.assertTrue(msg.is_flagged)
        self.assertIn('Lien externe', msg.flag_reason)
        self.assertIn('https://www.instagram.com/lucasfontayne/', msg.flag_reason)

        admin_mails = self._admin_mails()
        self.assertEqual(len(admin_mails), 1)
        self.assertIn('Lien externe', admin_mails[0].subject)
        self.assertIn('Casting Tartuffe', admin_mails[0].subject)
        self.assertNotIn('[Django]', admin_mails[0].subject)
        self.assertIn('https://www.instagram.com/lucasfontayne/', admin_mails[0].body)

    def test_flagged_message_still_delivered(self):
        self.client.post(
            reverse('messaging:conversation', args=[self.conv.pk]),
            {'body': 'lien suspect https://example.com'},
        )
        # Le message existe en base (flag ≠ blocage)…
        self.assertTrue(Message.objects.filter(conversation=self.conv, sender=self.alice).exists())
        # …et la notification "nouveau message" au destinataire part toujours.
        recipient_mails = [m for m in mail.outbox if m.to == ['bob@example.com']]
        self.assertEqual(len(recipient_mails), 1)

    def test_clean_message_not_flagged_no_admin_mail(self):
        self.client.post(
            reverse('messaging:conversation', args=[self.conv.pk]),
            {'body': 'Bonjour, je suis disponible pour une audition.'},
        )
        msg = Message.objects.get(conversation=self.conv, sender=self.alice)
        self.assertFalse(msg.is_flagged)
        self.assertEqual(self._admin_mails(), [])

    def test_new_conversation_with_link_notifies_admins(self):
        self.client.post(
            reverse('messaging:new_conversation', args=[self.offer.pk]),
            {'body': 'virement possible, contactez-moi'},
        )
        admin_mails = self._admin_mails()
        self.assertEqual(len(admin_mails), 1)
        self.assertIn('Motif financier', admin_mails[0].subject)

    def test_manual_report_unchanged(self):
        msg = Message.objects.create(conversation=self.conv, sender=self.bob, body='contenu déplacé')
        self.client.post(reverse('messaging:report_message', args=[msg.pk]), {'reason': 'spam'})
        manual_mails = [m for m in mail.outbox if '🚩 Message signalé' in m.subject]
        self.assertEqual(len(manual_mails), 1)
        html = manual_mails[0].alternatives[0][0]
        self.assertIn('alice@example.com', html)  # le signalant apparaît
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python manage.py test messaging -v 2`
Expected: `test_message_with_link_flags_and_notifies_admins` et `test_new_conversation_with_link_notifies_admins` FAIL (aucun mail avec « Détection auto » — l'actuel part avec le préfixe `[Django]` et sans label) ; les 3 autres PASS déjà (comportements préservés).

- [ ] **Step 3: Refactor `messaging/views.py`**

**3a — imports** : ligne 5, retirer `mail_admins` ; ligne 16, remplacer l'import moderation :

```python
from django.core.mail import send_mail
```

```python
from .moderation import get_flag_reason
```

**3b — `_send_report_notification`** : remplacer la fonction entière (l.49-98) par :

```python
def _send_report_notification(request, msg, reason, *, auto_label=None):
    """Notifie les admins d'un message signalé.

    Mode manuel (défaut) : signalé par request.user.
    Mode auto (auto_label fourni) : flaggé par la détection regex.
    """
    auto = auto_label is not None
    conv = msg.conversation
    admin_emails = [email for _, email in settings.ADMINS]
    if not admin_emails:
        return

    offer = conv.offer
    site_url = settings.SITE_URL

    # Enrichit chaque message avec son sender_display pour le template
    all_messages = list(conv.messages.select_related('sender').all())
    for m in all_messages:
        m.sender_display = _sender_display_name(m.sender) if m.sender else 'Utilisateur supprimé'

    context = {
        'is_auto': auto,
        'reporter_name': 'Détection automatique' if auto else _sender_display_name(request.user),
        'reporter_email': '' if auto else request.user.email,
        'reporter_profile_url': '' if auto else _user_profile_url(request, request.user),
        'sender_name': _sender_display_name(msg.sender),
        'sender_email': msg.sender.email if msg.sender else '—',
        'flag_reason': reason,
        'offer_title': offer.title if offer else '—',
        'offer_url': request.build_absolute_uri(f'/offer/{offer.pk}') if offer else '',
        'sender_profile_url': _user_profile_url(request, msg.sender),
        'admin_url': f'{site_url}/admin/messaging/message/{msg.pk}/change/',
        'site_url': site_url,
        'messages': all_messages,
        'reported_message_pk': msg.pk,
    }

    html_body = render_to_string('emails/report_notification.html', context)
    if auto:
        subject = f'[PAT] 🤖 Détection auto — {auto_label} — {context["offer_title"]}'
        text_body = (
            f'Message flaggé automatiquement #{msg.pk}\n'
            f'Détection : {auto_label}\n'
            f'Auteur : {context["sender_name"]} ({context["sender_email"]})\n'
            f'Raison : {reason}\n'
            f'Annonce : {context["offer_title"]}\n\n'
            f'Contenu :\n{msg.body}'
        )
    else:
        subject = f'[PAT] 🚩 Message signalé — {context["offer_title"]}'
        text_body = (
            f'Message signalé #{msg.pk}\n'
            f'Signalé par : {context["reporter_name"]}\n'
            f'Auteur : {context["sender_name"]}\n'
            f'Raison : {reason or "Non précisée"}\n'
            f'Annonce : {context["offer_title"]}\n\n'
            f'Contenu :\n{msg.body}'
        )
    try:
        send_mail(
            subject,
            text_body,
            settings.DEFAULT_FROM_EMAIL,
            admin_emails,
            html_message=html_body,
            fail_silently=False,
        )
    except Exception as e:
        logger.error('Échec envoi notification signalement (msg #%s) : %s', msg.pk, e)
```

**3c — `_apply_moderation`** : remplacer la fonction entière (l.161-173) par :

```python
def _apply_moderation(msg, body):
    """Flagge le message si suspect. Retourne (label, extrait) ou None."""
    reason = get_flag_reason(body)
    if reason:
        label, snippet = reason
        msg.is_flagged = True
        msg.flag_reason = f'Détection automatique — {label} : {snippet}'
    return reason
```

**3d — `conversation_detail`** : dans le bloc POST, remplacer

```python
            msg = Message(conversation=conv, sender=request.user, body=body)
            _apply_moderation(msg, body, request.user)
            msg.save()
            conv.save()
            if other:
                _send_notification(request, conv, msg, other)
```

par

```python
            msg = Message(conversation=conv, sender=request.user, body=body)
            flag = _apply_moderation(msg, body)
            msg.save()
            conv.save()
            if flag:
                _send_report_notification(request, msg, msg.flag_reason, auto_label=flag[0])
            if other:
                _send_notification(request, conv, msg, other)
```

**3e — `new_conversation`** : dans le bloc POST, remplacer

```python
            msg = Message(conversation=conv, sender=request.user, body=body)
            _apply_moderation(msg, body, request.user)
            msg.save()
            if offer.author:
                _send_notification(request, conv, msg, offer.author)
```

par

```python
            msg = Message(conversation=conv, sender=request.user, body=body)
            flag = _apply_moderation(msg, body)
            msg.save()
            if flag:
                _send_report_notification(request, msg, msg.flag_reason, auto_label=flag[0])
            if offer.author:
                _send_notification(request, conv, msg, offer.author)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python manage.py test messaging -v 2`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add messaging/views.py messaging/tests.py
git commit -m "feat(messaging): email admin riche pour le flag automatique"
```

---

### Task 3: Template `report_notification.html` — mode auto

**Files:**
- Modify: `templates/emails/report_notification.html` (l.15-17 header, l.31-34 ligne « Signalé par »)
- Modify: `messaging/tests.py` (1 test de rendu HTML)

- [ ] **Step 1: Write the failing test**

Ajouter à la classe `AutoFlagNotificationTests` :

```python
    def test_auto_email_html_shows_auto_detection(self):
        self.client.post(
            reverse('messaging:conversation', args=[self.conv.pk]),
            {'body': 'lien https://example.com/spam'},
        )
        html = self._admin_mails()[0].alternatives[0][0]
        self.assertIn('Message signalé automatiquement', html)
        self.assertIn('Détection automatique', html)
        self.assertIn('https://example.com/spam', html)
        self.assertNotIn('Profil signalant', html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python manage.py test messaging.tests.AutoFlagNotificationTests.test_auto_email_html_shows_auto_detection -v 2`
Expected: FAIL sur `assertIn('Message signalé automatiquement', html)` (le header dit encore « 🚩 Message signalé »)

- [ ] **Step 3: Modify the template**

Dans `templates/emails/report_notification.html` :

Header (l.15-17), remplacer

```html
          <p style="margin:0;font-size:18px;font-weight:bold;color:#fff;">
            🚩 Message signalé
          </p>
```

par

```html
          <p style="margin:0;font-size:18px;font-weight:bold;color:#fff;">
            {% if is_auto %}🤖 Message signalé automatiquement{% else %}🚩 Message signalé{% endif %}
          </p>
```

Ligne « Signalé par » (l.31-34), remplacer

```html
                  <tr>
                    <td style="padding:3px 0;font-size:12px;color:#6b7280;width:140px;">Signalé par</td>
                    <td style="padding:3px 0;font-size:12px;color:#1a1814;font-weight:bold;">{{ reporter_name }} <span style="font-weight:normal;color:#6b7280;">({{ reporter_email }})</span></td>
                  </tr>
```

par

```html
                  <tr>
                    <td style="padding:3px 0;font-size:12px;color:#6b7280;width:140px;">Signalé par</td>
                    <td style="padding:3px 0;font-size:12px;color:#1a1814;font-weight:bold;">{{ reporter_name }}{% if not is_auto %} <span style="font-weight:normal;color:#6b7280;">({{ reporter_email }})</span>{% endif %}</td>
                  </tr>
```

(En mode auto, `reporter_name` vaut « Détection automatique » — posé dans le contexte par la Task 2. Le bouton « Profil signalant » est déjà masqué car `reporter_profile_url` est vide et le template fait `{% if reporter_profile_url %}` — aucun changement nécessaire.)

- [ ] **Step 4: Run the full messaging suite**

Run: `uv run python manage.py test messaging -v 2`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add templates/emails/report_notification.html messaging/tests.py
git commit -m "feat(messaging): variante auto du template email de signalement"
```

---

### Task 4: Vérification finale

- [ ] **Step 1: Run the full project test suite**

Run: `uv run python manage.py test`
Expected: PASS — aucune régression dans les autres apps (le seul symbole partagé modifié est `messaging.moderation`, vérifier qu'aucun autre module ne l'importe : `grep -r "from messaging" --include="*.py"` ne doit montrer que des imports internes à `messaging/`).

- [ ] **Step 2: Commit final (si un fix a été nécessaire), sinon rien**
