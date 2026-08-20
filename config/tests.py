from django.test import RequestFactory, TestCase

from config.exception_filter import RedactedSettingsReporterFilter


class RedactedSettingsReporterFilterTests(TestCase):
    """Les identifiants de connexion ne doivent pas fuiter dans les rapports d'erreur."""

    def setUp(self):
        self.filter = RedactedSettingsReporterFilter()
        self.credential = 'redis://default:sup3rs3cr3t@redis.railway.internal:6379'

    def _cleansed(self, name, value):
        return self.filter.cleanse_setting(name, value)

    def test_redis_url_is_masked(self):
        self.assertNotIn('sup3rs3cr3t', str(self._cleansed('REDIS_URL', self.credential)))

    def test_celery_broker_url_is_masked(self):
        self.assertNotIn('sup3rs3cr3t', str(self._cleansed('CELERY_BROKER_URL', self.credential)))

    def test_celery_result_backend_is_masked(self):
        self.assertNotIn('sup3rs3cr3t', str(self._cleansed('CELERY_RESULT_BACKEND', self.credential)))

    def test_django_database_url_is_masked(self):
        dsn = 'postgres://user:sup3rs3cr3t@host/db'
        self.assertNotIn('sup3rs3cr3t', str(self._cleansed('DJANGO_DATABASE_URL', dsn)))

    def test_secret_key_is_still_masked(self):
        self.assertNotIn('sup3rs3cr3t', str(self._cleansed('SECRET_KEY', 'sup3rs3cr3t')))

    def test_harmless_settings_stay_readable(self):
        """Masquer trop large rendrait les rapports d'erreur inutiles."""
        self.assertEqual(
            self._cleansed('SITE_URL', 'https://petites-annonces-theatre.fr'),
            'https://petites-annonces-theatre.fr',
        )
        self.assertEqual(self._cleansed('STATIC_URL', '/static/'), '/static/')

    def test_filter_is_wired_into_settings(self):
        from django.views.debug import get_exception_reporter_filter

        request = RequestFactory().get('/')
        self.assertIsInstance(
            get_exception_reporter_filter(request),
            RedactedSettingsReporterFilter,
        )
