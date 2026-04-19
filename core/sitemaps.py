from django.contrib.sitemaps import Sitemap
from django.db.models import Count, Q
from django.urls import reverse
from django.utils.text import slugify

from core.models import Offer


class OfferSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.8

    def items(self):
        return Offer.objects.filter(filled=False).filter(
            Q(moderation__isnull=True) | Q(moderation__passed=True)
        ).order_by('-created_on')

    def lastmod(self, obj):
        return obj.created_on

    def location(self, obj):
        return reverse('offer', kwargs={'offer_id': obj.pk})


class CitySitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.7

    def items(self):
        from datetime import datetime, timedelta
        six_months_ago = datetime.now() - timedelta(days=180)
        cities_qs = (
            Offer.objects
            .filter(filled=False, created_on__gte=six_months_ago)
            .exclude(city='')
            .filter(Q(moderation__isnull=True) | Q(moderation__passed=True))
            .values('city')
            .annotate(count=Count('id'))
            .filter(count__gte=3)
            .order_by('-count')
        )
        return [slugify(c['city']) for c in cities_qs]

    def location(self, city_slug):
        return reverse('city_offers', kwargs={'city_slug': city_slug})


class DepartmentSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.7

    def items(self):
        from datetime import datetime, timedelta
        six_months_ago = datetime.now() - timedelta(days=180)
        cities = (
            Offer.objects
            .filter(filled=False, created_on__gte=six_months_ago)
            .exclude(city='')
            .filter(Q(moderation__isnull=True) | Q(moderation__passed=True))
            .values_list('city', flat=True)
        )
        dept_counts = {}
        for city in cities:
            parts = [p.strip() for p in city.split(',')]
            if len(parts) >= 3:
                candidate = parts[-2]
                if candidate.lower() not in ('france', 'belgique', 'suisse', 'luxembourg', 'canada'):
                    dept_counts[candidate] = dept_counts.get(candidate, 0) + 1
        return [slugify(dept) for dept, count in dept_counts.items() if count >= 3]

    def location(self, dept_slug):
        return reverse('department_offers', kwargs={'dept_slug': dept_slug})


class StaticSitemap(Sitemap):
    changefreq = 'monthly'
    priority = 0.5

    def items(self):
        return ['index', 'about', 'tou']

    def location(self, item):
        return reverse(item)
