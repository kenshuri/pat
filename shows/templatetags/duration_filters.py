# shows/templatetags/duration_filters.py
from django import template

register = template.Library()

@register.filter
def duration_human(value):
    if value is None:
        return ""
    total_minutes = int(value.total_seconds() // 60)
    hours = total_minutes // 60
    minutes = total_minutes % 60
    if hours and minutes:
        return f"{hours}h{minutes}"
    elif hours:
        return f"{hours}h"
    else:
        return f"{minutes} min"
