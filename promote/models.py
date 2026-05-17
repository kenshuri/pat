from django.db import models
from django.utils.text import slugify

from accounts.models import CustomUser


class Promote(models.Model):
    FORMULA_CHOICES = [
        ('day',   'Jour'),
        ('week',  'Semaine'),
        ('month', 'Mois'),
    ]
    STATUS_CHOICES = [
        ('pending_payment', 'En attente de paiement'),
        ('confirmed',       'Confirmé'),
        ('expired',         'Expiré'),
    ]

    # --- infos générales ----------------------------------------------------
    user   = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    title  = models.CharField(max_length=120)
    slug   = models.SlugField(unique=True, blank=True)

    # --- pièce associée (self-service) --------------------------------------
    play             = models.ForeignKey(
        'shows.Play', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='promotions',
    )
    stripe_session_id = models.CharField(max_length=255, blank=True, default='')
    formula           = models.CharField(
        max_length=10, choices=FORMULA_CHOICES, blank=True, default='',
    )
    status            = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending_payment',
    )

    # --- période de diffusion ----------------------------------------------
    start_date = models.DateField()
    end_date   = models.DateField()

    # --- statistiques -------------------------------------------------------
    impression_count    = models.PositiveIntegerField(default=0, editable=False)
    click_count         = models.PositiveIntegerField(default=0, editable=False)
    detail_view_count   = models.PositiveIntegerField(default=0, editable=False)
    booking_click_count = models.PositiveIntegerField(default=0, editable=False)

    # --- facturation --------------------------------------------------------
    price_paid = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
    )

    notifications_sent = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Bandeau promotionnel'
        verbose_name_plural = 'Bandeaux promotionnels'

    def __str__(self):
        return f"{self.title} ({self.user})"

    @property
    def duration_days(self):
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return None

    def save(self, *args, **kwargs):
        if not self.slug:
            if self.play and self.start_date:
                base = f"{self.play.title}-{self.start_date}"
            else:
                base = self.title
            candidate = slugify(base)[:50]
            slug = candidate
            counter = 1
            while Promote.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{candidate[:47]}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)
