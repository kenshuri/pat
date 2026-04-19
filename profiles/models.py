from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models
from django.utils.text import slugify
from PIL import Image, ImageOps

from accounts.models import CustomUser


def _actor_photo_path(instance, filename):
    env = getattr(settings, 'STORAGE_ENV', 'dev')
    return f"{env}/profiles/actors/{instance.pk}/photo.webp"


def _actor_extra_photo_path(instance, filename):
    env = getattr(settings, 'STORAGE_ENV', 'dev')
    return f"{env}/profiles/actors/{instance.actor_id}/photos/{instance.pk}.webp"


def _troupe_photo_path(instance, filename):
    env = getattr(settings, 'STORAGE_ENV', 'dev')
    return f"{env}/profiles/troupes/{instance.pk}/photo.webp"


def _troupe_extra_photo_path(instance, filename):
    env = getattr(settings, 'STORAGE_ENV', 'dev')
    return f"{env}/profiles/troupes/{instance.troupe_id}/photos/{instance.pk}.webp"


def _unique_slug(model_class, base_slug, exclude_pk=None):
    slug = base_slug or 'profil'
    i = 2
    while True:
        qs = model_class.objects.filter(slug=slug)
        if exclude_pk:
            qs = qs.exclude(pk=exclude_pk)
        if not qs.exists():
            return slug
        slug = f"{base_slug}-{i}"
        i += 1


def _process_image(image_field, max_w=800, max_h=800, quality=82):
    buffer = BytesIO()
    try:
        img = Image.open(image_field)
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.LANCZOS
        img.thumbnail((max_w, max_h), resample=resample)
        img.save(buffer, format="WEBP", quality=quality, method=6)
        buffer.seek(0)
        return ContentFile(buffer.getvalue())
    finally:
        buffer.close()


class ActorProfile(models.Model):
    user         = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='actor_profile')
    slug         = models.SlugField(max_length=80, unique=True, blank=True)
    display_name = models.CharField(max_length=80)
    city         = models.CharField(max_length=255, blank=True)
    bio          = models.TextField(max_length=2000, blank=True)
    photo        = models.ImageField(upload_to=_actor_photo_path, null=True, blank=True)
    video_url    = models.URLField(blank=True, help_text="Lien YouTube ou Vimeo")
    skills       = models.TextField(max_length=500, blank=True, help_text="Compétences, séparées par des virgules")
    experience   = models.TextField(max_length=3000, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.display_name} (@{self.user.email})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug(ActorProfile, slugify(self.display_name))
        elif self.pk:
            old = ActorProfile.objects.filter(pk=self.pk).values_list('display_name', flat=True).first()
            if old and old != self.display_name:
                self.slug = _unique_slug(ActorProfile, slugify(self.display_name), exclude_pk=self.pk)

        pending_photo = self.photo and not getattr(self.photo, '_committed', True)
        is_new = self.pk is None

        if pending_photo and is_new:
            pending_file = self.photo
            self.photo = None
            super().save(*args, **kwargs)
            content = _process_image(pending_file)
            self.photo.save("photo.webp", content, save=False)
            super().save(update_fields=['photo'])
        elif pending_photo:
            content = _process_image(self.photo)
            self.photo.save("photo.webp", content, save=False)
            super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    @property
    def skills_list(self):
        return [s.strip() for s in self.skills.split(',') if s.strip()]


class ActorPhoto(models.Model):
    actor = models.ForeignKey(ActorProfile, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to=_actor_extra_photo_path)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'pk']

    def __str__(self):
        return f"Photo #{self.pk} — {self.actor.display_name}"


class TroupeProfile(models.Model):
    user         = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='troupe_profile')
    slug         = models.SlugField(max_length=80, unique=True, blank=True)
    name         = models.CharField(max_length=120)
    city         = models.CharField(max_length=255, blank=True)
    description  = models.TextField(max_length=3000, blank=True)
    photo        = models.ImageField(upload_to=_troupe_photo_path, null=True, blank=True)
    website      = models.URLField(blank=True)
    founded_year = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} (@{self.user.email})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug(TroupeProfile, slugify(self.name))
        elif self.pk:
            old = TroupeProfile.objects.filter(pk=self.pk).values_list('name', flat=True).first()
            if old and old != self.name:
                self.slug = _unique_slug(TroupeProfile, slugify(self.name), exclude_pk=self.pk)

        pending_photo = self.photo and not getattr(self.photo, '_committed', True)
        is_new = self.pk is None

        if pending_photo and is_new:
            pending_file = self.photo
            self.photo = None
            super().save(*args, **kwargs)
            content = _process_image(pending_file)
            self.photo.save("photo.webp", content, save=False)
            super().save(update_fields=['photo'])
        elif pending_photo:
            content = _process_image(self.photo)
            self.photo.save("photo.webp", content, save=False)
            super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)


class TroupePhoto(models.Model):
    troupe = models.ForeignKey(TroupeProfile, on_delete=models.CASCADE, related_name='photos')
    image  = models.ImageField(upload_to=_troupe_extra_photo_path)
    order  = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'pk']

    def __str__(self):
        return f"Photo #{self.pk} — {self.troupe.name}"
