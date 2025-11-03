import os

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
    poster = models.ImageField(_("Affiche"), upload_to="posters/%Y/%m/", blank=True, null=True,)
    website = models.URLField(_("Site web"), blank=True, null=True)
    year_created = models.PositiveIntegerField(_("Année de création"), blank=True, null=True)

    created_at = models.DateTimeField(_("Date de création"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Date de modification"), auto_now=True)

    class Meta:
        verbose_name = _("Pièce")
        verbose_name_plural = _("Pièces")

    def __str__(self):
        return self.title

    # --- helper pour fabriquer un nom unique "slug-genre-YYYY[-N].webp" ---
    def _build_poster_name(self) -> str:
        """
        Construit un NOM DE FICHIER (sans répertoire) de la forme :
        '<slug>-<genre>-<année>[-N].webp'

        - Collision-safe via storage.exists() en testant le chemin complet.
        - On retourne UNIQUEMENT le nom (sans répertoire) : Django préfixe avec upload_to.
        """
        directory = timezone.now().strftime("posters/%Y/%m").strip("/")  # ex: 'posters/2025/10'
        base_slug = slugify(self.title)[:60] or "piece"
        date_str = self.year_created or timezone.now().year
        genre = self.genre or "other"
        base = f"{base_slug}-{genre}-{date_str}"
        ext = ".webp"

        storage = self.poster.storage

        candidate = f"{directory}/{base}{ext}"
        file_name = f"{base}{ext}"

        i = 1
        while storage.exists(candidate):
            candidate = f"{directory}/{base}-{i}{ext}"
            file_name = f"{base}-{i}{ext}"
            i += 1

        return file_name

    def save(self, *args, **kwargs):
        """
        Pipeline image côté serveur (sortie WebP) :

        - Ouverture Pillow + correction orientation EXIF.
        - Conservation de l’alpha si présent (WebP le supporte).
        - Redimension proportionnel max 1200x800 (LANCZOS).
        - Encodage WebP (quality=80, method=6 ; lossless=False).
        - Attribution d’un nom collision-safe (.webp) via _build_poster_name().
        - Enregistrement du fichier via FieldFile.save(save=False).
        - super().save() pour persister l’instance.

        NOTE :
        - Si vous utilisez save(update_fields=...), incluez "poster".
        - Nécessite Pillow compilé avec support WebP (libwebp).
        """
        if self.poster:
            buffer = None
            try:
                # 1) Ouvrir + corriger orientation EXIF (smartphones)
                img = Image.open(self.poster)
                img = ImageOps.exif_transpose(img)

                # 2) Normaliser le mode pour WebP
                #    - Si transparence -> conserver alpha (RGBA/LA)
                #    - Sinon, RGB suffit
                if img.mode == "P":
                    # Palette : si transparence attachée -> RGBA, sinon RGB
                    if "transparency" in img.info:
                        img = img.convert("RGBA")
                    else:
                        img = img.convert("RGB")
                elif img.mode == "LA":
                    img = img.convert("RGBA")
                elif img.mode not in ("RGB", "RGBA"):
                    # YCbCr, CMYK, etc. -> convertir
                    img = img.convert("RGBA" if "transparency" in img.info else "RGB")

                # 3) Redimension proportionnel : tient DANS 1200x800, sans crop
                try:
                    resample = Image.Resampling.LANCZOS
                except AttributeError:
                    resample = Image.LANCZOS
                img.thumbnail((1200, 800), resample=resample)

                # 4) Encodage WebP dans un buffer mémoire
                buffer = BytesIO()

                # Paramètres WebP :
                # - quality : 0–100 (80 = bon compromis)
                # - method : 0–6 (6 = plus lent mais meilleur)
                # - lossless : False (lossy) ; peut être mis à True pour graphiques plats
                save_kwargs = {
                    "format": "WEBP",
                    "quality": 80,
                    "method": 6,
                    "lossless": False,
                }

                # Si profil ICC présent, on le transmet (si supporté)
                icc = img.info.get("icc_profile")
                if icc:
                    save_kwargs["icc_profile"] = icc

                img.save(buffer, **save_kwargs)
                buffer.seek(0)

                # 5) Nom de fichier collision-safe (sans dossier)
                file_name = self._build_poster_name()

                # 6) Enregistrer le fichier sur le storage (Django ajoutera upload_to)
                self.poster.save(file_name, ContentFile(buffer.getvalue()), save=False)

            finally:
                if buffer is not None:
                    try:
                        buffer.close()
                    except Exception:
                        pass

        # 7) Sauvegarde du modèle (avec champ poster peuplé du chemin final)
        super().save(*args, **kwargs)


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

