from django import forms
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError
from django.core.files.images import get_image_dimensions
from .models import Play, Contributor, Representation


MAX_IMAGE_BYTES = 10_000_000
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/mpo"}
MAX_W, MAX_H = 8000, 8000


def _validate_image_field(f):
    if not f:
        return f
    size = getattr(f, "size", 0) or 0
    if size > MAX_IMAGE_BYTES:
        raise ValidationError("L'image dépasse la taille maximale autorisée (10 Mo).")
    ctype = getattr(f, "content_type", None)
    if ctype and ctype.lower() not in ALLOWED_CONTENT_TYPES:
        raise ValidationError("Format non supporté (formats acceptés : JPG, PNG, WEBP).")
    try:
        w, h = get_image_dimensions(f)
        if w and h and (w > MAX_W or h > MAX_H):
            raise ValidationError("L'image est trop grande (dimensions maximum 8000×8000 px).")
    except Exception:
        pass
    return f


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
            "title", "author", "company", "genre", "duration",
            "poster", "cover_image", "website", "year_created", "description",
        ]

    def clean_poster(self):
        return _validate_image_field(self.cleaned_data.get("poster"))

    def clean_cover_image(self):
        return _validate_image_field(self.cleaned_data.get("cover_image"))


class ContributorForm(forms.ModelForm):
    class Meta:
        model = Contributor
        fields = ["role", "name"]
        widgets = {
            "role": forms.TextInput(attrs={
                "class": "w-full border border-ink/20 px-3 py-2.5 text-sm text-ink focus:outline-none focus:border-ink transition-colors bg-surface",
                "placeholder": "Ex. Mise en scène, Acteur, Soprano…",
                "maxlength": 100,
            }),
            "name": forms.TextInput(attrs={
                "class": "w-full border border-ink/20 px-3 py-2.5 text-sm text-ink focus:outline-none focus:border-ink transition-colors bg-surface",
                "placeholder": "Nom(s)",
                "maxlength": 255,
            }),
        }
        labels = {"role": "Rôle", "name": "Nom(s)"}


ContributorFormSet = inlineformset_factory(
    parent_model=Play,
    model=Contributor,
    form=ContributorForm,
    fields=["role", "name"],
    extra=0,
    can_delete=True,
    validate_min=False,
    validate_max=False,
)
