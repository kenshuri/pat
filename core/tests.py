# pyright: reportAttributeAccessIssue=false

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import CustomUser
from core.models import Offer
from moderation.models import ModerationResult


class OfferModelTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email='tester@example.com',
            password='password123',
        )

    def test_defaults_and_str(self):
        offer = Offer.objects.create(  # type: ignore[attr-defined]
            title='Casting theatre',
            summary='Recherche comedien',
            author=self.user,
        )

        self.assertEqual(offer.type, Offer.OFFER)
        self.assertEqual(offer.section, Offer.ARTISTS_GROUPS)
        self.assertEqual(offer.category, Offer.UNPAID)
        self.assertIn('Casting theatre', str(offer))
        self.assertIn('tester@example.com', str(offer))

    def test_recent_property(self):
        offer = Offer.objects.create(  # type: ignore[attr-defined]
            title='Stage',
            summary='Stage de theatre',
            author=self.user,
        )
        self.assertTrue(offer.recent)

        older_than_week = timezone.now() - timedelta(weeks=2)
        Offer.objects.filter(pk=offer.pk).update(created_on=older_than_week)  # type: ignore[attr-defined]
        offer.refresh_from_db()
        self.assertFalse(offer.recent)

    def test_get_moderation_text_omits_empty_fields(self):
        moderation = ModerationResult.objects.create(passed=True, reasons='')  # type: ignore[attr-defined]
        offer = Offer.objects.create(  # type: ignore[attr-defined]
            title='Annonce',
            summary='Resume',
            description='Details',
            city='',
            min_age=None,
            max_age=None,
            gender=None,
            author=self.user,
            moderation=moderation,
        )

        moderation_text = offer.get_moderation_text()

        self.assertIn('Type:', moderation_text)
        self.assertIn('Catégorie:', moderation_text)
        self.assertIn('Titre:', moderation_text)
        self.assertIn('Résumé:', moderation_text)
        self.assertIn('Description:', moderation_text)
        self.assertNotIn('Ville:', moderation_text)
        self.assertNotIn('Âge minimum:', moderation_text)
        self.assertNotIn('Âge maximum:', moderation_text)
        self.assertNotIn('Genre:', moderation_text)
