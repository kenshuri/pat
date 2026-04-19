from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from shows.models import Play


class PlaySitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.7

    def items(self):
        return Play.objects.order_by('-created_at')

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return reverse('shows:play_detail', kwargs={'pk': obj.pk})
