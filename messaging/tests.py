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
