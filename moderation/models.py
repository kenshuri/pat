from django.db import models
from django.utils.translation import gettext_lazy as _

from moderation.utils import CATEGORY_TRANSLATIONS


class ModerationStatus(models.TextChoices):
    NOT_REVIEWED = "not_reviewed", _("Non révisé")
    REVIEW_REQUESTED = "review_requested", _("Révision demandée par l’auteur")
    REVIEW_PASSED = "review_passed", _("Révisé et accepté")
    REVIEW_FAILED = "review_failed", _("Révisé et rejeté")


class ModerationResult(models.Model):
    passed = models.BooleanField(default=False)
    reasons = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    manual_status = models.CharField(
        max_length=32,
        choices=ModerationStatus.choices,
        default=ModerationStatus.NOT_REVIEWED
    )

    def reasons_list(self):
        if self.reasons:
            return [r.strip() for r in self.reasons.split(",")]
        return []

    def get_localized_reasons(self):
        raw_reasons = self.reasons_list()
        return [CATEGORY_TRANSLATIONS.get(r, r) for r in raw_reasons]

    def __str__(self):
        return f"{'✅' if self.passed else '❌'} - {self.created_at.strftime('%Y-%m-%d %H:%M')} - {self.get_manual_status_display()}"
