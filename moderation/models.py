from django.db import models

from moderation.utils import CATEGORY_TRANSLATIONS, NON_BLOCKING_CATEGORIES


class ModerationResult(models.Model):
    reasons = models.TextField(blank=True, null=True)
    images_passed = models.BooleanField(null=True, blank=True)
    image_reasons = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def reasons_list(self):
        if self.reasons:
            return [r.strip() for r in self.reasons.split(",")]
        return []

    def blocking_reasons_list(self):
        """Raisons qui empêchent la publication automatique."""
        return [r for r in self.reasons_list() if r not in NON_BLOCKING_CATEGORIES]

    @property
    def has_blocking_reasons(self):
        return bool(self.blocking_reasons_list())

    @property
    def has_pii(self):
        """Des informations personnelles ont été repérées dans le texte."""
        return 'pii' in self.reasons_list()

    def get_localized_reasons(self):
        raw_reasons = self.reasons_list()
        return [CATEGORY_TRANSLATIONS.get(r, r) for r in raw_reasons]

    def __str__(self):
        status = "✅" if not self.reasons else "❌"
        return f"{status} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"
