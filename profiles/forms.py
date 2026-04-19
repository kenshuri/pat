from django import forms
from .models import ActorProfile, TroupeProfile


class ActorProfileForm(forms.ModelForm):
    class Meta:
        model = ActorProfile
        fields = ['display_name', 'city', 'bio', 'photo', 'video_url', 'skills', 'experience']
        labels = {
            'display_name': 'Nom affiché',
            'city':         'Ville',
            'bio':          'Présentation courte',
            'photo':        'Photo',
            'video_url':    'Vidéo (YouTube / Vimeo)',
            'skills':       'Compétences',
            'experience':   'Expérience',
        }
        help_texts = {
            'skills':   'Ex : comédie, chant, danse, mime — séparées par des virgules.',
            'video_url': "URL complète d'une vidéo de présentation.",
        }
        widgets = {
            'display_name': forms.TextInput(attrs={'placeholder': 'Prénom Nom'}),
            'city':         forms.TextInput(attrs={'placeholder': 'Paris, Île-de-France, France'}),
            'bio':          forms.Textarea(attrs={'rows': 4, 'placeholder': 'Quelques mots sur vous…'}),
            'skills':       forms.TextInput(attrs={'placeholder': 'comédie, chant, danse…'}),
            'experience':   forms.Textarea(attrs={'rows': 6, 'placeholder': 'Formations, spectacles, rôles…'}),
            'video_url':    forms.URLInput(attrs={'placeholder': 'https://youtube.com/…'}),
        }


class TroupeProfileForm(forms.ModelForm):
    class Meta:
        model = TroupeProfile
        fields = ['name', 'city', 'description', 'photo', 'website', 'founded_year']
        labels = {
            'name':         'Nom de la troupe',
            'city':         'Ville',
            'description':  'Présentation',
            'photo':        'Photo de profil',
            'website':      'Site internet',
            'founded_year': 'Année de création',
        }
        widgets = {
            'name':         forms.TextInput(attrs={'placeholder': 'Compagnie du Masque'}),
            'city':         forms.TextInput(attrs={'placeholder': 'Lyon, Auvergne-Rhône-Alpes, France'}),
            'description':  forms.Textarea(attrs={'rows': 6, 'placeholder': 'Histoire, répertoire, style…'}),
            'website':      forms.URLInput(attrs={'placeholder': 'https://…'}),
            'founded_year': forms.NumberInput(attrs={'placeholder': '2010', 'min': 1800, 'max': 2100}),
        }
