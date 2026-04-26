import json
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from accounts.models import CustomUser
from shows.models import Play
from promote.models import Promote
import stripe

_SIMPLE_STORAGE = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


class PromoteModelTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email='promo@example.com', password='password123'
        )
        self.play = Play.objects.create(
            user=self.user, title='Roméo et Juliette',
            genre='theatre', moderation_status='published',
        )

    def test_default_status_is_pending_payment(self):
        promo = Promote(
            user=self.user,
            title='Test',
            start_date=date.today(),
            end_date=date.today() + timedelta(days=6),
        )
        self.assertEqual(promo.status, 'pending_payment')

    def test_slug_generated_from_play_and_date(self):
        start = date(2026, 5, 10)
        promo = Promote.objects.create(
            user=self.user,
            play=self.play,
            title=self.play.title,
            start_date=start,
            end_date=start + timedelta(days=6),
            formula='week',
        )
        self.assertEqual(promo.slug, 'romeo-et-juliette-2026-05-10')

    def test_slug_generated_from_title_when_no_play(self):
        promo = Promote.objects.create(
            user=self.user,
            title='Mon spectacle',
            start_date=date.today(),
            end_date=date.today(),
        )
        self.assertIn('mon-spectacle', promo.slug)

    def test_slug_collision_appends_counter(self):
        start = date(2026, 6, 1)
        Promote.objects.create(
            user=self.user, play=self.play, title=self.play.title,
            start_date=start, end_date=start, formula='day',
        )
        promo2 = Promote.objects.create(
            user=self.user, play=self.play, title=self.play.title,
            start_date=start, end_date=start, formula='day',
        )
        self.assertNotEqual(promo2.slug, 'romeo-et-juliette-2026-06-01')
        self.assertTrue(promo2.slug.startswith('romeo-et-juliette'))


@override_settings(STORAGES=_SIMPLE_STORAGE)
class SponsorListViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            email='list@example.com', password='password123'
        )
        self.play = Play.objects.create(
            user=self.user, title='Ma Pièce',
            genre='theatre', moderation_status='published',
        )

    def test_redirects_anonymous(self):
        response = self.client.get(reverse('promote:sponsor_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])

    def test_shows_published_plays(self):
        self.client.login(email='list@example.com', password='password123')
        response = self.client.get(reverse('promote:sponsor_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ma Pièce')

    def test_redirects_to_calendar_with_play_param(self):
        self.client.login(email='list@example.com', password='password123')
        response = self.client.get(
            reverse('promote:sponsor_list'), {'play': self.play.pk}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('calendar', response['Location'])


@override_settings(STORAGES=_SIMPLE_STORAGE)
class AvailabilityViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            email='avail@example.com', password='password123'
        )

    def test_returns_json(self):
        self.client.login(email='avail@example.com', password='password123')
        response = self.client.get(reverse('promote:sponsor_availability'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        data = json.loads(response.content)
        self.assertIn('booked', data)

    def test_includes_confirmed_promos(self):
        play = Play.objects.create(
            user=self.user, title='Test Play',
            genre='theatre', moderation_status='published',
        )
        Promote.objects.create(
            user=self.user, play=play, title=play.title,
            start_date=date(2026, 7, 1), end_date=date(2026, 7, 7),
            formula='week', status='confirmed',
        )
        self.client.login(email='avail@example.com', password='password123')
        response = self.client.get(reverse('promote:sponsor_availability'))
        data = json.loads(response.content)
        slugs = [(b['start'], b['end']) for b in data['booked']]
        self.assertIn(('2026-07-01', '2026-07-07'), slugs)


@override_settings(STORAGES=_SIMPLE_STORAGE)
class CheckoutViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            email='checkout@example.com', password='password123'
        )
        self.play = Play.objects.create(
            user=self.user, title='Test Play',
            genre='theatre', moderation_status='published',
        )

    def _mock_session(self):
        session = MagicMock()
        session.id = 'cs_test_abc123'
        session.url = 'https://checkout.stripe.com/pay/cs_test_abc123'
        return session

    @patch('promote.views.stripe')
    def test_checkout_creates_promote_and_redirects(self, mock_stripe):
        mock_stripe.checkout.Session.create.return_value = self._mock_session()
        self.client.login(email='checkout@example.com', password='password123')
        response = self.client.post(
            reverse('promote:sponsor_checkout', args=[self.play.pk]),
            {'formula': 'week', 'start_date': '2026-08-01'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], 'https://checkout.stripe.com/pay/cs_test_abc123')
        promote = Promote.objects.get(stripe_session_id='cs_test_abc123')
        self.assertEqual(promote.status, 'pending_payment')
        self.assertEqual(promote.formula, 'week')

    @patch('promote.views.stripe')
    def test_checkout_rejects_overlapping_slot(self, mock_stripe):
        Promote.objects.create(
            user=self.user, play=self.play, title=self.play.title,
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 7),
            formula='week', status='confirmed',
        )
        self.client.login(email='checkout@example.com', password='password123')
        response = self.client.post(
            reverse('promote:sponsor_checkout', args=[self.play.pk]),
            {'formula': 'week', 'start_date': '2026-08-03'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('calendar', response['Location'])
        self.assertFalse(mock_stripe.checkout.Session.create.called)

    def test_checkout_rejects_non_owner(self):
        other = CustomUser.objects.create_user(
            email='other@example.com', password='password123'
        )
        self.client.login(email='other@example.com', password='password123')
        response = self.client.post(
            reverse('promote:sponsor_checkout', args=[self.play.pk]),
            {'formula': 'week', 'start_date': '2026-09-01'},
        )
        self.assertEqual(response.status_code, 404)

    def test_checkout_rejects_unpublished_play(self):
        self.play.moderation_status = 'pending'
        self.play.save()
        self.client.login(email='checkout@example.com', password='password123')
        response = self.client.post(
            reverse('promote:sponsor_checkout', args=[self.play.pk]),
            {'formula': 'week', 'start_date': '2026-09-01'},
        )
        self.assertEqual(response.status_code, 404)


class WebhookViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            email='webhook@example.com', password='password123'
        )
        self.play = Play.objects.create(
            user=self.user, title='Webhook Play',
            genre='theatre', moderation_status='published',
        )
        self.promote = Promote.objects.create(
            user=self.user, play=self.play, title=self.play.title,
            start_date=date(2026, 9, 1), end_date=date(2026, 9, 7),
            formula='week', status='pending_payment',
            stripe_session_id='cs_test_webhook',
        )

    def _post_webhook(self, event):
        with patch('promote.views.stripe') as mock_stripe:
            mock_stripe.Webhook.construct_event.return_value = event
            response = self.client.post(
                reverse('promote:stripe_webhook'),
                data=b'{}',
                content_type='application/json',
                HTTP_STRIPE_SIGNATURE='t=1,v1=abc',
            )
        return response

    def test_webhook_confirms_promote_on_completed(self):
        event = {
            'type': 'checkout.session.completed',
            'data': {'object': {
                'metadata': {'promote_id': str(self.promote.pk)},
                'amount_total': 1000,
            }},
        }
        response = self._post_webhook(event)
        self.assertEqual(response.status_code, 200)
        self.promote.refresh_from_db()
        self.assertEqual(self.promote.status, 'confirmed')
        self.assertEqual(float(self.promote.price_paid), 10.0)

    def test_webhook_returns_200_on_invalid_signature(self):
        with patch('promote.views.stripe.Webhook.construct_event') as mock_construct:
            mock_construct.side_effect = stripe.error.SignatureVerificationError("invalid sig", "sig_header")
            response = self.client.post(
                reverse('promote:stripe_webhook'),
                data=b'bad',
                content_type='application/json',
                HTTP_STRIPE_SIGNATURE='bad',
            )
        self.assertEqual(response.status_code, 200)

    def test_webhook_ignores_other_events(self):
        event = {
            'type': 'payment_intent.created',
            'data': {'object': {}},
        }
        response = self._post_webhook(event)
        self.assertEqual(response.status_code, 200)
        self.promote.refresh_from_db()
        self.assertEqual(self.promote.status, 'pending_payment')

    def test_webhook_skips_confirm_on_overlap(self):
        other_play = Play.objects.create(
            user=self.user, title='Other Play',
            genre='theatre', moderation_status='published',
        )
        Promote.objects.create(
            user=self.user, play=other_play, title='Other',
            start_date=date(2026, 9, 3), end_date=date(2026, 9, 5),
            formula='day', status='confirmed',
        )
        event = {
            'type': 'checkout.session.completed',
            'data': {'object': {
                'metadata': {'promote_id': str(self.promote.pk)},
                'amount_total': 1000,
            }},
        }
        response = self._post_webhook(event)
        self.assertEqual(response.status_code, 200)
        self.promote.refresh_from_db()
        self.assertEqual(self.promote.status, 'pending_payment')


@override_settings(STORAGES=_SIMPLE_STORAGE)
class ConfirmationViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            email='conf@example.com', password='password123'
        )
        self.play = Play.objects.create(
            user=self.user, title='Conf Play',
            genre='theatre', moderation_status='published',
        )
        self.promote = Promote.objects.create(
            user=self.user, play=self.play, title=self.play.title,
            start_date=date(2026, 10, 1), end_date=date(2026, 10, 7),
            formula='week', status='confirmed',
            stripe_session_id='cs_test_confirm123',
            price_paid='10.00',
        )

    def test_confirmation_shows_promote_details(self):
        self.client.login(email='conf@example.com', password='password123')
        response = self.client.get(
            reverse('promote:sponsor_confirmation', args=['cs_test_confirm123'])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Conf Play')

    def test_confirmation_requires_ownership(self):
        other = CustomUser.objects.create_user(
            email='other2@example.com', password='password123'
        )
        self.client.login(email='other2@example.com', password='password123')
        response = self.client.get(
            reverse('promote:sponsor_confirmation', args=['cs_test_confirm123'])
        )
        self.assertEqual(response.status_code, 404)

    def test_cancel_page_renders(self):
        self.client.login(email='conf@example.com', password='password123')
        response = self.client.get(reverse('promote:sponsor_cancel'))
        self.assertEqual(response.status_code, 200)
