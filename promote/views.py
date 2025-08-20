from urllib.parse import urlparse

from django.db.models import F
from django.http import HttpResponseBadRequest
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import DetailView
from django.template.loader import select_template
from promote.models import Promote


# Create your views here.
def default(request):
    return render(request, 'promote/default.html')


def banner_click(request, slug):
    promo = get_object_or_404(Promote, slug=slug)

    Promote.objects.filter(pk=promo.pk).update(
        click_count = F("click_count") + 1
    )

    # redirige vers la page détail
    return redirect("promote:detail", slug=slug)

class PromoteDetailView(DetailView):
    model = Promote
    context_object_name = "promo"
    slug_field = "slug"      # (default, but explicit)
    slug_url_kwarg = "slug"  # (default, but explicit)

    # ↓ dynamic template resolution
    def get_template_names(self):
        """
        1. Try  promote/<slug>.html          (e.g. promote/romeo-et-juliette.html)
        2. Fallback to promote/promote.html  (generic template)
        """
        slug = self.kwargs.get(self.slug_url_kwarg)
        candidates = [
            f"promote/details_{slug}.html",
            "promote/details_your-ad.html",
        ]
        # select_template returns the first template that actually exists
        return [select_template(candidates).template.name]

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)

        # obj existe maintenant
        Promote.objects.filter(pk=self.object.pk).update(
            detail_view_count=F("detail_view_count") + 1
        )
        return response


def booking_redirect(request, slug):
    promo = get_object_or_404(Promote, slug=slug)

    # 1) compteur atomique
    Promote.objects.filter(pk=promo.pk).update(
        booking_click_count=F("booking_click_count") + 1
    )

    # 2) URL externe passée dans ?next=
    target = request.GET.get("next")
    if not target:
        return redirect("promote:detail", slug=slug)

    # (optionnel) sécurise un peu : refuse javascript: etc.
    if urlparse(target).scheme not in ("http", "https"):
        return HttpResponseBadRequest("URL non valide.")

    return redirect(target)