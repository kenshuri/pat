from django import forms
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError
from django.core.files.images import get_image_dimensions
from .models import Play, Contributor, Representation


MAX_POSTER_BYTES = 10_000_000  # 10 Mo
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/mpo"}
MAX_W, MAX_H = 8000, 8000  # bornes de sécurité facultatives

class RepresentationForm(forms.ModelForm):
    class Meta:
        model = Representation
        fields = ["datetime", "venue", "city", "ticket_url"]
        widgets = {
            "datetime": forms.DateTimeInput(attrs={
                "type": "datetime-local",
                "class": "input input-bordered",
                "required": True
            }),
            "venue": forms.TextInput(attrs={
                "class": "input input-bordered",
                "required": True
            }),
            "city": forms.TextInput(attrs={
                "class": "input input-bordered",
            }),
            "ticket_url": forms.URLInput(attrs={
                "class": "input input-bordered"
            }),
        }
        labels = {
            "datetime": "Date & Heure",
            "venue": "Lieu",
            "city": "Ville",
            "ticket_url": "Lien billetterie"
        }


class PlayForm(forms.ModelForm):
    class Meta:
        model = Play
        fields = [
            "title",
            "author",
            "company",
            "genre",
            "duration",
            "poster",
            "website",
            "year_created",
            "description",
        ]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "input input-bordered w-full",
                "placeholder": "Titre de la pièce",
                "maxlength": 200
            }),
            "author": forms.TextInput(attrs={
                "class": "input input-bordered w-full",
                "placeholder": "Auteur·e (facultatif)"
            }),
            "company": forms.TextInput(attrs={
                "class": "input input-bordered w-full",
                "placeholder": "Nom de la compagnie (facultatif)"
            }),
            "genre": forms.Select(attrs={
                "class": "select select-bordered w-full"
            }),
            "duration": forms.TimeInput(attrs={
                "class": "input input-bordered w-full",
                "type": "time",
                "step": "60"
            }),
            "poster": forms.ClearableFileInput(attrs={
                "class": "file-input file-input-bordered w-full"
            }),
            "website": forms.URLInput(attrs={
                "class": "input input-bordered w-full",
                "placeholder": "https://site-web-de-la-pièce.com"
            }),
            "year_created": forms.NumberInput(attrs={
                "class": "input input-bordered w-full",
                "placeholder": "Année de création",
                "min": 1800,
                "max": 2100
            }),
            "description": forms.Textarea(attrs={
                "class": "textarea textarea-bordered w-full",
                "placeholder": "Décris la pièce : thème, intentions, synopsis...",
                "rows": 5
            }),
        }

    def clean_poster(self):
        f = self.cleaned_data.get("poster")
        if not f:
            return f

        # 1) Taille
        size = getattr(f, "size", 0) or 0
        if size > MAX_POSTER_BYTES:
            raise ValidationError("L'image dépasse la taille maximale autorisée (10 Mo).")

        # 2) Type MIME (si disponible)
        ctype = getattr(f, "content_type", None)
        if ctype and ctype.lower() not in ALLOWED_CONTENT_TYPES:
            raise ValidationError("Format non supporté (formats acceptés : JPG, PNG, WEBP).")

        # 3) Dimensions (évite les images anormales)
        try:
            w, h = get_image_dimensions(f)
            if w and h and (w > MAX_W or h > MAX_H):
                raise ValidationError("L'image est trop grande (dimensions maximum 8000×8000 px).")
        except Exception:
            # Si on ne peut pas lire les dimensions, on laisse PIL gérer plus loin
            pass

        return f


class ContributorForm(forms.ModelForm):
    class Meta:
        model = Contributor
        fields = ["role", "name"]
        widgets = {
            "role": forms.TextInput(attrs={"class": "input input-bordered w-full", "placeholder": "Rôle (ex. Mise en scène, Acteur, Soprano…)", "maxlength": 100}),
            "name": forms.TextInput(attrs={"class": "input input-bordered w-full", "placeholder": "Nom(s)", "maxlength": 255}),
        }
        labels = {"role": "Rôle", "name": "Nom(s)"}


ContributorFormSet = inlineformset_factory(
    parent_model=Play,
    model=Contributor,
    form=ContributorForm,
    fields=["role", "name"],
    extra=0,            # pas de lignes par défaut; on ajoute dynamiquement
    can_delete=True,    # permet de marquer une ligne à supprimer
    validate_min=False,
    validate_max=False,
)
