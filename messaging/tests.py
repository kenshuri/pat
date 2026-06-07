from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from core.models import Offer
from .models import Conversation, Message
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

    def test_link_trailing_punctuation_stripped(self):
        _, snippet = get_flag_reason('mon profil : https://example.com/page.')
        self.assertEqual(snippet, 'https://example.com/page')

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
        # Use a fresh offer so no pre-existing conversation triggers an early redirect
        offer2 = Offer.objects.create(title='Pièce sans conv', summary='Résumé', author=self.bob)
        self.client.post(
            reverse('messaging:new_conversation', args=[offer2.pk]),
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
