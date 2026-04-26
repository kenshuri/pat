import os
import uuid

from django.core.validators import FileExtensionValidator
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify
from django.utils import timezone
from PIL import Image, ImageOps
from io import BytesIO
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from moderation.models import ModerationResult


def _play_poster_path(instance, filename):
    env = getattr(settings, 'STORAGE_ENV', 'dev')
    return f"{env}/posters/{instance.pk}/poster.webp"


def _play_cover_path(instance, filename):
    env = getattr(settings, 'STORAGE_ENV', 'dev')
    return f"{env}/posters/{instance.pk}/cover.webp"


def _play_photo_path(instance, filename):
    env = getattr(settings, 'STORAGE_ENV', 'dev')
    return f"{env}/posters/{instance.play_id}/photos/{instance.pk}.webp"


def _process_image(source_field, target_name):
    """Resize, EXIF-correct, encode as WebP and save back to the field."""
    buffer = None
    try:
        img = Image.open(source_field)
        img = ImageOps.exif_transpose(img)
        if img.mode == "P":
            img = img.convert("RGBA" if "transparency" in img.info else "RGB")
        elif img.mode == "LA":
            img = img.convert("RGBA")
        elif img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "transparency" in img.info else "RGB")
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.LANCZOS
        img.thumbnail((1200, 800), resample=resample)
        buffer = BytesIO()
        save_kwargs = {"format": "WEBP", "quality": 80, "method": 6, "lossless": False}
        icc = img.info.get("icc_profile")
        if icc:
            save_kwargs["icc_profile"] = icc
        img.save(buffer, **save_kwargs)
        buffer.seek(0)
        source_field.save(target_name, ContentFile(buffer.getvalue()), save=False)
    finally:
        if buffer is not None:
            try:
                buffer.close()
            except Exception:
                pass


class Play(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='plays')
    title = models.CharField(_("Titre de la pièce"), max_length=200)
    author = models.CharField(_("Auteur"), max_length=200, blank=True, null=True)
    company = models.CharField(_("Compagnie"), max_length=200, blank=True, null=True)
    description = models.TextField(_("Description"), blank=True)

    class Genre(models.TextChoices):
        THEATRE = 'theatre', _("Théâtre")
        DANCE = 'dance', _("Danse")
        LYRIC = 'lyric', _("Lyrique")
        CIRCUS = 'circus', _("Cirque")
        YOUTH = 'youth', _("Jeune public")
        OTHER = 'other', _("Autres")

    genre = models.CharField(_("Genre"), max_length=20, choices=Genre.choices)
    duration = models.DurationField(_("Durée"), blank=True, null=True)
    poster = models.ImageField(_("Affiche"), upload_to=_play_poster_path, blank=True, null=True)
    cover_image = models.ImageField(_("Photo de couverture"), upload_to=_play_cover_path, blank=True, null=True)
    website = models.URLField(_("Site web"), blank=True, null=True)
    year_created = models.PositiveIntegerField(_("Année de création"), blank=True, null=True)

    created_at = models.DateTimeField(_("Date de création"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Date de modification"), auto_now=True)

    # --- Modération ---
    PENDING      = 'pending'
    PUBLISHED    = 'published'
    UNDER_REVIEW = 'under_review'
    REJECTED     = 'rejected'
    MODERATION_STATUS_CHOICES = [
        (PENDING,      'En vérification'),
        (PUBLISHED,    'Publiée'),
        (UNDER_REVIEW, 'Sous examen'),
        (REJECTED,     'Rejetée'),
    ]

    moderation_status = models.CharField(
        max_length=20,
        choices=MODERATION_STATUS_CHOICES,
        default=PENDING,
    )
    moderation = models.ForeignKey(
        ModerationResult,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='plays',
    )

    class Meta:
        verbose_name = _("Pièce")
        verbose_name_plural = _("Pièces")

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        pending_poster = self.poster and not getattr(self.poster, '_committed', True)
        pending_cover = self.cover_image and not getattr(self.cover_image, '_committed', True)
        is_new = self.pk is None

        if is_new and (pending_poster or pending_cover):
            saved_poster = self.poster if pending_poster else None
            saved_cover = self.cover_image if pending_cover else None
            if pending_poster:
                self.poster = None
            if pending_cover:
                self.cover_image = None
            super().save(*args, **kwargs)

            update_fields = []
            if saved_poster:
                self.poster = saved_poster
                _process_image(self.poster, "poster.webp")
                update_fields.append('poster')
            if saved_cover:
                self.cover_image = saved_cover
                _process_image(self.cover_image, "cover.webp")
                update_fields.append('cover_image')

            super(Play, self).save(update_fields=update_fields)
        else:
            if pending_poster:
                _process_image(self.poster, "poster.webp")
            if pending_cover:
                _process_image(self.cover_image, "cover.webp")
            super().save(*args, **kwargs)


class PlayPhoto(models.Model):
    play = models.ForeignKey(Play, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to=_play_photo_path)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'pk']

    def __str__(self):
        return f"Photo #{self.pk} — {self.play.title}"


class Contributor(models.Model):
    play = models.ForeignKey(Play, on_delete=models.CASCADE, related_name="contributors")
    role = models.CharField(_("Rôle"), max_length=100)
    name = models.CharField(_("Nom(s)"), max_length=255)

    class Meta:
        verbose_name = _("Contributeur")
        verbose_name_plural = _("Contributeurs")
        ordering = ["role", "name"]

    def __str__(self):
        return f"{self.role} – {self.name}"


class Representation(models.Model):
    play = models.ForeignKey(Play, on_delete=models.CASCADE, related_name='representations')
    datetime = models.DateTimeField(_("Date et heure"))
    venue = models.CharField(_("Lieu"), max_length=255)
    city = models.CharField(_("Ville"), max_length=100, blank=True, null=True)
    price = models.CharField(_("Tarif"), max_length=50, blank=True)
    ticket_url = models.URLField(_("Lien vers la billetterie"), blank=True, null=True)

    created_at = models.DateTimeField(_("Date de création"), auto_now_add=True)

    class Meta:
        verbose_name = _("Représentation")
        verbose_name_plural = _("Représentations")

    def __str__(self):
        return f"{self.play.title} - {self.datetime.strftime('%d/%m/%Y %H:%M')}"


class PublicationCredit(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='publication_credit')
    remaining_credits = models.IntegerField(_("Crédits restants"), default=0)

    class Meta:
        verbose_name = _("Crédit de publication")
        verbose_name_plural = _("Crédits de publication")

    def __str__(self):
        return f"{self.user.username}: {self.remaining_credits} crédits"


class PlayMembership(models.Model):
    DIRECTION_INVITE  = 'invite'
    DIRECTION_REQUEST = 'request'
    DIRECTION_CHOICES = [
        (DIRECTION_INVITE,  'Invitation'),
        (DIRECTION_REQUEST, 'Demande'),
    ]

    STATUS_PENDING   = 'pending'
    STATUS_ACCEPTED  = 'accepted'
    STATUS_DECLINED  = 'declined'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_PENDING,   'En attente'),
        (STATUS_ACCEPTED,  'Accepté'),
        (STATUS_DECLINED,  'Refusé'),
        (STATUS_CANCELLED, 'Annulée'),
    ]

    play         = models.ForeignKey(Play, on_delete=models.CASCADE, related_name='memberships')
    user         = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='play_memberships')
    email        = models.EmailField()
    role         = models.CharField(max_length=100, blank=True)
    direction    = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    status       = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    token        = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='initiated_memberships')
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Participation'
        verbose_name_plural = 'Participations'
        unique_together = [('play', 'email')]

    def __str__(self):
        return f"{self.email} — {self.play.title} ({self.get_status_display()})"


class Transaction(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='transactions')
    date = models.DateTimeField(_("Date de la transaction"), auto_now_add=True)
    amount = models.DecimalField(_("Montant (€)"), max_digits=6, decimal_places=2)
    credits_purchased = models.IntegerField(_("Crédits achetés"))

    class Meta:
        verbose_name = _("Transaction")
        verbose_name_plural = _("Transactions")

    def __str__(self):
        return f"{self.user.username} - {self.credits_purchased} crédits - {self.amount} €"
