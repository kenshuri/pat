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


from unittest.mock import patch, MagicMock
from moderation.models import ModerationResult


class ModeratePlayImagesTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email='tester2@example.com',
            password='password123',
        )

    def test_no_images_returns_passed(self):
        from core.services.image_moderation import moderate_play_images
        play = Play.objects.create(
            user=self.user, title='No Images', genre='theatre'
        )
        passed, reasons = moderate_play_images(play)
        self.assertTrue(passed)
        self.assertEqual(reasons, '')

    @patch('core.services.image_moderation._download_to_temp')
    @patch('core.services.image_moderation._analyze_image_file')
    def test_safe_poster_returns_passed(self, mock_analyze, mock_download):
        from core.services.image_moderation import moderate_play_images
        mock_download.return_value = '/tmp/fake.webp'
        mock_analyze.return_value = True

        play = Play.objects.create(
            user=self.user, title='Safe Poster', genre='theatre'
        )
        # Simuler un poster sans vraiment uploader
        play.poster = MagicMock()
        play.poster.name = 'poster.webp'

        passed, reasons = moderate_play_images(play)
        self.assertTrue(passed)

    @patch('core.services.image_moderation._download_to_temp')
    @patch('core.services.image_moderation._analyze_image_file')
    def test_unsafe_poster_returns_failed(self, mock_analyze, mock_download):
        from core.services.image_moderation import moderate_play_images
        mock_download.return_value = '/tmp/fake.webp'
        mock_analyze.return_value = False  # unsafe

        play = Play.objects.create(
            user=self.user, title='Unsafe Poster', genre='theatre'
        )
        play.poster = MagicMock()
        play.poster.name = 'poster.webp'

        passed, reasons = moderate_play_images(play)
        self.assertFalse(passed)
        self.assertIn('poster', reasons)


class ModeratePlayTaskTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email='task_tester@example.com',
            password='password123',
        )

    def _make_play(self):
        return Play.objects.create(
            user=self.user,
            title='Test Play',
            description='Une description de test',
            genre='theatre',
        )

    @patch('core.services.image_moderation.moderate_play_images')
    @patch('moderation.services.moderate_text')
    def test_published_when_text_and_images_pass(self, mock_text, mock_images):
        from core.tasks import moderate_play
        mock_text.return_value = ModerationResult.objects.create(reasons=None)
        mock_images.return_value = (True, '')

        play = self._make_play()
        moderate_play(play.pk)

        play.refresh_from_db()
        self.assertEqual(play.moderation_status, 'published')
        self.assertIsNotNone(play.moderation)

    @patch('core.services.image_moderation.moderate_play_images')
    @patch('moderation.services.moderate_text')
    def test_under_review_when_text_fails(self, mock_text, mock_images):
        from core.tasks import moderate_play
        mock_text.return_value = ModerationResult.objects.create(reasons='violence')
        mock_images.return_value = (True, '')

        play = self._make_play()
        moderate_play(play.pk)

        play.refresh_from_db()
        self.assertEqual(play.moderation_status, 'under_review')

    @patch('core.services.image_moderation.moderate_play_images')
    @patch('moderation.services.moderate_text')
    def test_under_review_when_images_fail(self, mock_text, mock_images):
        from core.tasks import moderate_play
        mock_text.return_value = ModerationResult.objects.create(reasons=None)
        mock_images.return_value = (False, 'poster')

        play = self._make_play()
        moderate_play(play.pk)

        play.refresh_from_db()
        self.assertEqual(play.moderation_status, 'under_review')

    def test_does_not_raise_on_missing_play(self):
        from core.tasks import moderate_play
        # Should log warning and return, not raise
        moderate_play(99999)
