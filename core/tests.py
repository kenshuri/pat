# pyright: reportAttributeAccessIssue=false

from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from core.models import Offer
from moderation.models import ModerationResult

_SIMPLE_STORAGE = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


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
        moderation = ModerationResult.objects.create(reasons='')  # type: ignore[attr-defined]
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


@override_settings(ADMINS=[('Admin', 'admin@example.com')])
class ModerateOfferTaskTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email='tester@example.com',
            password='password123',
        )

    def _make_offer(self):
        return Offer.objects.create(  # type: ignore[attr-defined]
            title='Annonce',
            summary='Resume',
            author=self.user,
        )

    @patch('core.services.image_moderation.moderate_images')
    @patch('moderation.services.moderate_text')
    def test_pii_alone_publishes_the_offer(self, mock_text, mock_images):
        from core.tasks import moderate_offer
        mock_text.return_value = ModerationResult.objects.create(reasons='pii')  # type: ignore[attr-defined]
        mock_images.return_value = (True, '')

        offer = self._make_offer()
        moderate_offer(offer.pk)

        offer.refresh_from_db()
        self.assertEqual(offer.moderation_status, Offer.PUBLISHED)

    @patch('core.services.image_moderation.moderate_images')
    @patch('moderation.services.moderate_text')
    def test_pii_alone_does_not_notify_admins(self, mock_text, mock_images):
        from core.tasks import moderate_offer
        mock_text.return_value = ModerationResult.objects.create(reasons='pii')  # type: ignore[attr-defined]
        mock_images.return_value = (True, '')

        moderate_offer(self._make_offer().pk)

        self.assertEqual(mail.outbox, [])

    @patch('core.services.image_moderation.moderate_images')
    @patch('moderation.services.moderate_text')
    def test_pii_with_another_category_stays_under_review(self, mock_text, mock_images):
        from core.tasks import moderate_offer
        mock_text.return_value = ModerationResult.objects.create(  # type: ignore[attr-defined]
            reasons='pii, violence_and_threats'
        )
        mock_images.return_value = (True, '')

        offer = self._make_offer()
        moderate_offer(offer.pk)

        offer.refresh_from_db()
        self.assertEqual(offer.moderation_status, Offer.UNDER_REVIEW)
        self.assertEqual(len(mail.outbox), 1)

    @patch('core.services.image_moderation.moderate_images')
    @patch('moderation.services.moderate_text')
    def test_pii_with_failing_images_stays_under_review(self, mock_text, mock_images):
        from core.tasks import moderate_offer
        mock_text.return_value = ModerationResult.objects.create(reasons='pii')  # type: ignore[attr-defined]
        mock_images.return_value = (False, 'photo_1')

        offer = self._make_offer()
        moderate_offer(offer.pk)

        offer.refresh_from_db()
        self.assertEqual(offer.moderation_status, Offer.UNDER_REVIEW)


@override_settings(STORAGES=_SIMPLE_STORAGE)
class PiiOwnerWarningTests(TestCase):
    """L'avertissement « déplacez vos coordonnées » n'est visible que par l'auteur."""

    WARNING_SNIPPET = 'Vos coordonnées sont visibles de tous'

    def setUp(self):
        self.client = Client()
        self.author = CustomUser.objects.create_user(
            email='author@example.com',
            password='password123',
        )
        self.visitor = CustomUser.objects.create_user(
            email='visitor@example.com',
            password='password123',
        )

    def _make_offer(self, reasons):
        return Offer.objects.create(  # type: ignore[attr-defined]
            title='Annonce',
            summary='Resume',
            author=self.author,
            moderation_status=Offer.PUBLISHED,
            moderation=ModerationResult.objects.create(reasons=reasons),  # type: ignore[attr-defined]
        )

    def test_author_sees_warning_when_pii_flagged(self):
        offer = self._make_offer('pii')
        self.client.login(email='author@example.com', password='password123')

        response = self.client.get(reverse('offer', args=[offer.pk]))

        self.assertContains(response, self.WARNING_SNIPPET)

    def test_author_does_not_see_warning_without_pii(self):
        offer = self._make_offer(None)
        self.client.login(email='author@example.com', password='password123')

        response = self.client.get(reverse('offer', args=[offer.pk]))

        self.assertNotContains(response, self.WARNING_SNIPPET)

    def test_other_user_never_sees_warning(self):
        offer = self._make_offer('pii')
        self.client.login(email='visitor@example.com', password='password123')

        response = self.client.get(reverse('offer', args=[offer.pk]))

        self.assertNotContains(response, self.WARNING_SNIPPET)

    def test_anonymous_visitor_never_sees_warning(self):
        offer = self._make_offer('pii')

        response = self.client.get(reverse('offer', args=[offer.pk]))

        self.assertNotContains(response, self.WARNING_SNIPPET)
