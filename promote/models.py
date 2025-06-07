from django.db import models
from django.utils.text import slugify

from accounts.models import CustomUser

# Create your models here.
class Promote(models.Model):
    # --- infos générales ----------------------------------------------------
    user   = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    title  = models.CharField(max_length=120)
    slug   = models.SlugField(unique=True, blank=True)

    # --- période de diffusion ----------------------------------------------
    start_date = models.DateField()
    end_date   = models.DateField()

    # --- statistiques -------------------------------------------------------
    impression_count    = models.PositiveIntegerField(default=0, editable=False)
    click_count         = models.PositiveIntegerField(default=0, editable=False)
    detail_view_count   = models.PositiveIntegerField(default=0, editable=False)
    booking_click_count = models.PositiveIntegerField(default=0, editable=False)

    # --- facturation --------------------------------------------------------
    price_paid   = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Bandeau promotionnel"
        verbose_name_plural = "Bandeaux promotionnels"

    # -----------------------------------------------------------------------

    def __str__(self):
        return f"{self.title} ({self.user})"

    # --- helpers ------------------------------------------------------------

    @property
    def duration_days(self):
        """
            Renvoie le nombre de jours inclusifs,
            ou None si start_date / end_date sont manquants.
            """
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return None

    def save(self, *args, **kwargs):
        # slug automatique
        if not self.slug:
            self.slug = slugify(self.title)[:50]

        super().save(*args, **kwargs)