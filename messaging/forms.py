from django import forms


class MessageForm(forms.Form):
    body = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 5,
            'placeholder': 'Votre message…',
            'class': (
                'w-full border border-ink/20 px-3 py-2.5 text-sm text-ink '
                'focus:outline-none focus:border-ink transition-colors bg-surface resize-y'
            ),
        }),
        max_length=5000,
        label='Message',
    )


class ReportForm(forms.Form):
    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Décrivez pourquoi ce message vous semble problématique (optionnel)…',
            'class': (
                'w-full border border-ink/20 px-3 py-2.5 text-sm text-ink '
                'focus:outline-none focus:border-ink transition-colors bg-surface resize-y'
            ),
        }),
        max_length=1000,
        required=False,
        label='Raison du signalement',
    )
