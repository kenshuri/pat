from django.contrib.auth.forms import UserCreationForm
from django.forms import ModelForm
from django_email_blacklist import DisposableEmailChecker
from turnstile.fields import TurnstileField

from accounts.models import CustomUser
from core.models import Offer

class OfferForm(ModelForm):
    turnstile = TurnstileField()

    class Meta:
        model = Offer
        fields = ['type','category','title',
                  'summary',
                  'description',
                  'city',
                  'min_age',
                  'max_age',
                  'gender',
                  'show_author_mail',
                  'contact_name',
                  'contact_email',
                  'contact_phone',
                  'contact_website',
                  'contact_details',
                  ]
        labels = {
            'type': "Type d'annonce",
            'category': 'Catégorie',
            'title': "Titre de l'annonce",
            'summary': 'Résumé',
            'city': 'Ville',
            'min_age': 'Âge apparent minimal',
            'max_age': 'Âge apparent maximal',
            'gender': 'Genre',
            'show_author_mail': 'Afficher Email utilisateur',
            'contact_name': 'Nom du contact',
            'contact_email': 'Email',
            'contact_phone': 'Numéro de téléphone',
            'contact_website': 'Site internet',
            'contact_details': 'Infos supplémentaires',
        }



class SignUpForm(UserCreationForm):
    turnstile = TurnstileField()

    class Meta:
        model = CustomUser
        fields = ('email', 'password1', 'password2', )

    def __init__(self, *args, **kwargs):
        super(SignUpForm, self).__init__(*args, **kwargs)
        self.fields['password1'].help_text = 'Le mot doit faire plus de 8 caractères, ne pas être un mot de passe trop commun et ne pas être entièrement numérique.'

    def clean_email(self):
        email = self.cleaned_data['email']
        email_checker = DisposableEmailChecker()
        if email_checker.is_disposable(email):
            self.add_error('email', 'Utilisez une adresse email non-jetable svp')
        return email

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error('password2', "Les deux mots de passe sont différents")
        return password2

