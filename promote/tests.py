import json
from datetime import date, timedelta
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from accounts.models import CustomUser
from shows.models import Play
from promote.models import Promote

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
