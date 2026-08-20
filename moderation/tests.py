# pyright: reportAttributeAccessIssue=false

from django.test import TestCase

from moderation.models import ModerationResult


class BlockingReasonsTests(TestCase):
    def test_no_reasons_is_not_blocking(self):
        result = ModerationResult.objects.create(reasons=None)

        self.assertEqual(result.blocking_reasons_list(), [])
        self.assertFalse(result.has_blocking_reasons)

    def test_pii_alone_is_not_blocking(self):
        result = ModerationResult.objects.create(reasons='pii')

        self.assertEqual(result.blocking_reasons_list(), [])
        self.assertFalse(result.has_blocking_reasons)

    def test_pii_stays_visible_in_reasons(self):
        result = ModerationResult.objects.create(reasons='pii')

        self.assertEqual(result.reasons_list(), ['pii'])
        self.assertIn(
            "Partage ou demande d'informations personnelles",
            result.get_localized_reasons(),
        )

    def test_pii_combined_with_another_category_is_blocking(self):
        result = ModerationResult.objects.create(reasons='pii, violence_and_threats')

        self.assertEqual(result.blocking_reasons_list(), ['violence_and_threats'])
        self.assertTrue(result.has_blocking_reasons)

    def test_api_error_is_blocking(self):
        result = ModerationResult.objects.create(reasons='api_error')

        self.assertTrue(result.has_blocking_reasons)
