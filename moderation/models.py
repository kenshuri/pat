from django.db import models

from moderation.utils import CATEGORY_TRANSLATIONS


class ModerationResult(models.Model):
    reasons = models.TextField(blank=True, null=True)
    images_passed = models.BooleanField(null=True, blank=True)
    image_reasons = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def reasons_list(self):
        if self.reasons:
            return [r.strip() for r in self.reasons.split(",")]
        return []

    def get_localized_reasons(self):
        raw_reasons = self.reasons_list()
        return [CATEGORY_TRANSLATIONS.get(r, r) for r in raw_reasons]

    def __str__(self):
        status = "✅" if not self.reasons else "❌"
        return f"{status} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"
