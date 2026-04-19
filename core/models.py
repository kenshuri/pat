# Create your models here.
import uuid
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models
from django.db.models import CheckConstraint, Q
from django.db.models.fields import CharField
from django.utils.html import strip_tags
from django.utils.text import slugify

from accounts.models import CustomUser
import datetime

from django.utils import timezone
from PIL import Image, ImageOps

from moderation.models import ModerationResult


def _offer_cover_path(instance, filename):
    env = getattr(settings, 'STORAGE_ENV', 'dev')
    return f"{env}/offers/{instance.pk}/cover.webp"


def _offer_photo_path(instance, filename):
    env = getattr(settings, 'STORAGE_ENV', 'dev')
    return f"{env}/offers/{instance.offer_id}/photos/{instance.pk}.webp"


class Offer(models.Model):
    OFFER = 'offer'
    DEMAND = 'demand'
    PAID = 'paid'
    UNPAID = 'unpaid'
    MALE = 'male'
    FEMALE = 'female'
    OTHER = 'other'

    TYPE_CHOICES = [
        (OFFER, 'Offre'),
        (DEMAND, 'Demande'),
    ]

    # Rubriques principales du site
    ARTISTS_GROUPS = 'artists_groups'
    COURSES_TRAINING = 'courses_training'
    CALLS_EVENTS = 'calls_events'
    SERVICES_EQUIPMENT = 'services_equipment'

    SECTION_CHOICES = [
        (ARTISTS_GROUPS, 'Artistes & Groupes'),
        (COURSES_TRAINING, 'Cours & Formations'),
        (CALLS_EVENTS, 'Appels & Événements'),
        (SERVICES_EQUIPMENT, 'Services & Matériel'),
    ]

    CATEGORY_CHOICES = [
        (UNPAID, 'Bénévole'),
        (PAID, 'Rémunéré'),
    ]

    GENDER_CHOICES = [
        (OTHER, 'Non-Binaire'),
        (FEMALE, 'Femme'),
        (MALE, 'Homme'),
    ]

    type = models.CharField(
        max_length=255,
        choices=TYPE_CHOICES,
        default=OFFER,
    )

    section = models.CharField(
        max_length=255,
        choices=SECTION_CHOICES,
        default=ARTISTS_GROUPS)

    category = models.CharField(
        max_length=255,
        choices=CATEGORY_CHOICES,
        default=UNPAID,
    )

    title = models.CharField(max_length=50, null=False)
    summary = models.CharField(max_length=255, null=False)
    description = models.TextField(max_length=5000, blank=True)
    city = models.CharField(max_length=255, blank=True)
    min_age = models.PositiveIntegerField(null=True, blank=True)
    max_age = models.PositiveIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=255, choices=GENDER_CHOICES, default=None, null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    filled = models.BooleanField(default=False)
    author = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True)
    show_author_mail = models.BooleanField(default=False)
    contact_name = models.CharField(max_length=255, null=True, blank=True)
    contact_email = models.EmailField(null=True, blank=True)
    contact_phone = models.CharField(max_length=255, null=True, blank=True)
    contact_website = models.URLField(null=True, blank=True)
    contact_details = models.TextField(null=True, blank=True)
    moderation = models.ForeignKey(ModerationResult, null=True, blank=True, on_delete=models.SET_NULL, related_name="offers")

    cover_image = models.ImageField(
        upload_to=_offer_cover_path,
        null=True,
        blank=True,
        help_text="Image principale / couverture de l'annonce (optionnelle).",
    )

    def __str__(self):
        return f'{self.title} - {self.author} - {self.created_on.strftime("%Y-%m-%d, %H:%M")}'

    @property
    def department(self):
        """Extrait le département/région du champ city (format Mapbox : 'Ville, Département, France')."""
        if not self.city:
            return ''
        parts = [p.strip() for p in self.city.split(',')]
        if len(parts) >= 3:
            candidate = parts[-2]
            if candidate.lower() not in ('france', 'belgique', 'suisse', 'luxembourg', 'canada'):
                return candidate
        return ''

    @property
    def recent(self):
        offer_date = self.created_on
        threshold = timezone.now() - datetime.timedelta(weeks=1)
        return offer_date > threshold


    @property
    def has_extra_photos(self):
        return self.photos.exists()

    def _process_cover_image(self):
        buffer = None
        try:
            img = Image.open(self.cover_image)
            img = ImageOps.exif_transpose(img)
            if img.mode == "P":
                img = img.convert("RGBA" if "transparency" in img.info else "RGB")
            elif img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            try:
                resample = Image.Resampling.LANCZOS
            except AttributeError:
                resample = Image.LANCZOS
            img.thumbnail((1200, 800), resample=resample)
            buffer = BytesIO()
            img.save(buffer, format="WEBP", quality=80, method=6)
            buffer.seek(0)
            self.cover_image.save("cover.webp", ContentFile(buffer.getvalue()), save=False)
        finally:
            if buffer:
                buffer.close()

    def save(self, *args, **kwargs):
        pending_image = self.cover_image and not getattr(self.cover_image, '_committed', True)
        is_new = self.pk is None

        if pending_image and is_new:
            pending_file = self.cover_image
            self.cover_image = None
            super().save(*args, **kwargs)
            self.cover_image = pending_file
            self._process_cover_image()
            super(Offer, self).save(update_fields=['cover_image'])
        elif pending_image:
            self._process_cover_image()
            super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    def get_moderation_text(self) -> str:
        """
        Retourne une chaîne de texte contenant toutes les informations importantes de l'annonce,
        formatée pour être soumise à la modération de contenu.
        """
        details = [
            f"Type: {self.get_type_display()}",
            f"Catégorie: {self.get_category_display()}",
            f"Titre: {self.title}",
            f"Résumé: {self.summary}",
            f"Description: {strip_tags(self.description)}",
            f"Ville: {self.city}" if self.city else None,
            f"Âge minimum: {self.min_age}" if self.min_age else None,
            f"Âge maximum: {self.max_age}" if self.max_age else None,
            f"Genre: {self.get_gender_display()}" if self.gender else None,
        ]

        # Filtrer les valeurs None et joindre les éléments par une nouvelle ligne
        return "\n".join(filter(None, details))


class Alert(models.Model):
    IMMEDIATE = 'immediate'
    DAILY = 'daily'
    WEEKLY = 'weekly'
    FREQUENCY_CHOICES = [
        (IMMEDIATE, 'Immédiatement'),
        (DAILY, 'Quotidiennement'),
        (WEEKLY, 'Hebdomadairement'),
    ]

    email      = models.EmailField()
    search     = models.CharField(max_length=255, blank=True)
    section    = models.CharField(max_length=50, blank=True)
    offer_type = models.CharField(max_length=50, blank=True)
    category   = models.CharField(max_length=50, blank=True)
    gender     = models.CharField(max_length=50, blank=True)
    age_min    = models.PositiveIntegerField(null=True, blank=True)
    age_max    = models.PositiveIntegerField(null=True, blank=True)
    frequency  = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default=DAILY)
    token      = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    confirmed  = models.BooleanField(default=False)
    active     = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['email'])]

    def __str__(self):
        return f"Alerte {self.email} — {self.get_frequency_display()}"

    def filter_summary(self):
        """Retourne une description lisible des filtres actifs."""
        parts = []
        section_labels = {
            'artists_groups': 'Comédien·nes', 'courses_training': 'Cours',
            'calls_events': 'Appels', 'services_equipment': 'Services',
        }
        type_labels = {'offer': 'Offre', 'demand': 'Demande'}
        category_labels = {'paid': 'Rémunéré', 'unpaid': 'Bénévole'}
        gender_labels = {'male': 'Homme', 'female': 'Femme', 'other': 'Non-binaire'}
        if self.search:
            parts.append(f'"{self.search}"')
        if self.section:
            parts.append(section_labels.get(self.section, self.section))
        if self.offer_type:
            parts.append(type_labels.get(self.offer_type, self.offer_type))
        if self.category:
            parts.append(category_labels.get(self.category, self.category))
        if self.gender:
            parts.append(gender_labels.get(self.gender, self.gender))
        if self.age_min and self.age_max:
            parts.append(f'{self.age_min}–{self.age_max} ans')
        elif self.age_min:
            parts.append(f'{self.age_min}+ ans')
        elif self.age_max:
            parts.append(f'–{self.age_max} ans')
        return ', '.join(parts) if parts else 'Toutes les annonces'


class OfferPhoto(models.Model):
    """Photos supplémentaires associées à une annonce."""
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to=_offer_photo_path)
    order = models.PositiveSmallIntegerField(default=0, help_text="Ordre d'affichage (0 = premier).")

    class Meta:
        ordering = ['order', 'pk']

    def __str__(self):
        return f"Photo #{self.pk} — {self.offer.title}"
