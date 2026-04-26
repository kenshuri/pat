from datetime import date, timedelta
from django.test import TestCase
from accounts.models import CustomUser
from shows.models import Play
from promote.models import Promote


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
