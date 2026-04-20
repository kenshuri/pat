from django import template
from django.urls import reverse

register = template.Library()


@register.filter
def display_name(user):
    if user is None:
        return 'Utilisateur supprimé'
    try:
        name = user.actor_profile.display_name
        if name:
            return name
    except Exception:
        pass
    try:
        name = user.troupe_profile.name
        if name:
            return name
    except Exception:
        pass
    return f'utilisateur-{user.pk}'


@register.filter
def profile_url(user):
    if user is None:
        return ''
    return reverse('profiles:user_detail', kwargs={'pk': user.pk})
