# shows/templatetags/placeholder_tags.py
from django import template
import urllib.parse
import textwrap

register = template.Library()

@register.filter
def wrap_for_placeholder(title, width=15):
    """
    Coupe un titre trop long en plusieurs lignes (avec \\n)
    pour un affichage harmonieux sur placehold.co
    """
    if not title:
        return ""

    # On coupe le texte intelligemment autour des espaces
    wrapped = "\n".join(textwrap.wrap(title, width=width, break_long_words=False))
    # On encode le résultat pour une URL (placehold.co attend un texte encodé)
    return urllib.parse.quote(wrapped)
