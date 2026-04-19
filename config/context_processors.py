from datetime import datetime, timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.utils.text import slugify


def site_url(request):
    from core.models import Offer

    six_months_ago = datetime.now() - timedelta(days=180)
    top_cities_qs = (
        Offer.objects
        .filter(filled=False, created_on__gte=six_months_ago)
        .exclude(city='')
        .filter(Q(moderation__isnull=True) | Q(moderation__passed=True))
        .values('city')
        .annotate(count=Count('id'))
        .filter(count__gte=3)
        .order_by('-count')[:12]
    )
    top_cities = [(c['city'], slugify(c['city'])) for c in top_cities_qs]

    cities_for_dept = (
        Offer.objects
        .filter(filled=False, created_on__gte=six_months_ago)
        .exclude(city='')
        .filter(Q(moderation__isnull=True) | Q(moderation__passed=True))
        .values_list('city', flat=True)
    )
    dept_counts = {}
    for city_val in cities_for_dept:
        parts = [p.strip() for p in city_val.split(',')]
        if len(parts) >= 3:
            candidate = parts[-2]
            if candidate.lower() not in ('france', 'belgique', 'suisse', 'luxembourg', 'canada'):
                dept_counts[candidate] = dept_counts.get(candidate, 0) + 1
    top_departments = sorted(
        [(dept, slugify(dept)) for dept, count in dept_counts.items() if count >= 3],
        key=lambda x: -dept_counts[x[0]]
    )[:10]

    return {
        'SITE_URL': settings.SITE_URL,
        'top_cities': top_cities,
        'top_departments': top_departments,
    }
