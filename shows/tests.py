from django.test import TestCase
from accounts.models import CustomUser
from shows.models import Play


class PlayModerationStatusTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email='tester@example.com',
            password='password123',
        )

    def test_default_moderation_status_is_pending(self):
        play = Play.objects.create(
            user=self.user,
            title='Test Play',
            genre='theatre',
        )
        self.assertEqual(play.moderation_status, 'pending')

    def test_moderation_status_choices(self):
        play = Play.objects.create(
            user=self.user,
            title='Test Play',
            genre='theatre',
        )
        for status in ('pending', 'published', 'under_review', 'rejected'):
            play.moderation_status = status
            play.save()
            play.refresh_from_db()
            self.assertEqual(play.moderation_status, status)

    def test_moderation_fk_nullable(self):
        play = Play.objects.create(
            user=self.user,
            title='Test Play',
            genre='theatre',
        )
        self.assertIsNone(play.moderation)
