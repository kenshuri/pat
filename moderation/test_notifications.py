# pyright: reportAttributeAccessIssue=false

from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.test import RequestFactory, TestCase

from accounts.models import CustomUser
from core.admin import OfferAdmin
from core.models import Offer
from moderation.models import ModerationResult
from shows.admin import PlayAdmin
from shows.models import Play


class _RequestMixin:
    def _request(self):
        request = RequestFactory().post('/admin/')
        request.user = self.staff
        # message_user() a besoin du framework de messages
        setattr(request, 'session', {})
        setattr(request, '_messages', FallbackStorage(request))
        return request


class OfferDecisionNotificationTests(_RequestMixin, TestCase):
    def setUp(self):
        self.admin = OfferAdmin(Offer, AdminSite())
        self.staff = CustomUser.objects.create_superuser(
            email='staff@example.com', password='password123',
        )
        self.author = CustomUser.objects.create_user(
            email='author@example.com', password='password123',
        )

    def _make_offer(self, status=Offer.UNDER_REVIEW, reasons='violence_and_threats'):
        return Offer.objects.create(
            title='Annonce',
            summary='Resume',
            author=self.author,
            moderation_status=status,
            moderation=ModerationResult.objects.create(reasons=reasons),
        )

    def test_validating_notifies_the_author(self):
        offer = self._make_offer()

        self.admin.valider_annonces(self._request(), Offer.objects.filter(pk=offer.pk))

        offer.refresh_from_db()
        self.assertEqual(offer.moderation_status, Offer.PUBLISHED)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['author@example.com'])

    def test_rejecting_notifies_the_author_with_reasons(self):
        offer = self._make_offer()

        self.admin.rejeter_annonces(self._request(), Offer.objects.filter(pk=offer.pk))

        offer.refresh_from_db()
        self.assertEqual(offer.moderation_status, Offer.REJECTED)
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].alternatives[0][0]
        self.assertIn('Violence ou menaces', body)

    def test_revalidating_a_published_offer_sends_nothing(self):
        offer = self._make_offer(status=Offer.PUBLISHED)

        self.admin.valider_annonces(self._request(), Offer.objects.filter(pk=offer.pk))

        self.assertEqual(mail.outbox, [])

    def test_offer_without_author_does_not_crash(self):
        offer = Offer.objects.create(
            title='Sans auteur', summary='Resume', author=None,
            moderation_status=Offer.UNDER_REVIEW,
        )

        self.admin.valider_annonces(self._request(), Offer.objects.filter(pk=offer.pk))

        offer.refresh_from_db()
        self.assertEqual(offer.moderation_status, Offer.PUBLISHED)
        self.assertEqual(mail.outbox, [])

    def test_changing_status_in_the_form_notifies_the_author(self):
        """Couvre le formulaire de modification et la colonne list_editable."""
        offer = self._make_offer()
        offer.moderation_status = Offer.PUBLISHED

        self.admin.save_model(self._request(), offer, form=None, change=True)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['author@example.com'])

    def test_saving_without_status_change_sends_nothing(self):
        offer = self._make_offer(status=Offer.PUBLISHED)
        offer.title = 'Titre modifié'

        self.admin.save_model(self._request(), offer, form=None, change=True)

        self.assertEqual(mail.outbox, [])

    @patch('core.services.image_moderation.moderate_images')
    @patch('moderation.services.moderate_text')
    def test_automatic_publication_does_not_notify_the_author(self, mock_text, mock_images):
        """Une publication automatique ne doit jamais écrire à l'auteur."""
        from core.tasks import moderate_offer
        mock_text.return_value = ModerationResult.objects.create(reasons=None)
        mock_images.return_value = (True, '')
        offer = self._make_offer(status=Offer.PENDING, reasons=None)

        moderate_offer(offer.pk)

        offer.refresh_from_db()
        self.assertEqual(offer.moderation_status, Offer.PUBLISHED)
        self.assertEqual(mail.outbox, [])


class PlayDecisionNotificationTests(_RequestMixin, TestCase):
    def setUp(self):
        self.admin = PlayAdmin(Play, AdminSite())
        self.staff = CustomUser.objects.create_superuser(
            email='staff@example.com', password='password123',
        )
        self.owner = CustomUser.objects.create_user(
            email='owner@example.com', password='password123',
        )

    def _make_play(self, status='under_review'):
        return Play.objects.create(
            user=self.owner,
            title='Ma Piece',
            genre='theatre',
            moderation_status=status,
            moderation=ModerationResult.objects.create(reasons='violence_and_threats'),
        )

    def test_validating_notifies_the_owner(self):
        play = self._make_play()

        self.admin.valider_pieces(self._request(), Play.objects.filter(pk=play.pk))

        play.refresh_from_db()
        self.assertEqual(play.moderation_status, 'published')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['owner@example.com'])

    def test_rejecting_notifies_the_owner_with_reasons(self):
        play = self._make_play()

        self.admin.rejeter_pieces(self._request(), Play.objects.filter(pk=play.pk))

        play.refresh_from_db()
        self.assertEqual(play.moderation_status, 'rejected')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Violence ou menaces', mail.outbox[0].alternatives[0][0])

    def test_revalidating_a_published_play_sends_nothing(self):
        play = self._make_play(status='published')

        self.admin.valider_pieces(self._request(), Play.objects.filter(pk=play.pk))

        self.assertEqual(mail.outbox, [])
