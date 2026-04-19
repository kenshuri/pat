import os

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404

from accounts.models import CustomUser

from core.models import Offer
from shows.models import Play

from .forms import ActorProfileForm, TroupeProfileForm
from .models import ActorPhoto, ActorProfile, TroupePhoto, TroupeProfile
from profiles.models import _process_image


def _save_actor_photos(actor, files):
    existing_count = actor.photos.count()
    for i, file in enumerate(files):
        photo = ActorPhoto(actor=actor, order=existing_count + i)
        photo.save()
        content = _process_image(file, max_w=1200, max_h=1600)
        photo.image.save(f"{photo.pk}.webp", content, save=True)


def _delete_actor_photos(actor, post_data):
    for key in post_data:
        if key.startswith('delete_photo_'):
            pk = key.split('_')[-1]
            actor.photos.filter(pk=pk).delete()


def _save_troupe_photos(troupe, files):
    existing_count = troupe.photos.count()
    for i, file in enumerate(files):
        photo = TroupePhoto(troupe=troupe, order=existing_count + i)
        photo.save()
        content = _process_image(file, max_w=1200, max_h=1600)
        photo.image.save(f"{photo.pk}.webp", content, save=True)


def _delete_troupe_photos(troupe, post_data):
    for key in post_data:
        if key.startswith('delete_photo_'):
            pk = key.split('_')[-1]
            troupe.photos.filter(pk=pk).delete()


# ── Comédiens ─────────────────────────────────────────────────────────────────

def actor_detail(request, slug):
    actor = get_object_or_404(ActorProfile, slug=slug)
    own = request.user.is_authenticated and actor.user == request.user
    troupe_profile = getattr(actor.user, 'troupe_profile', None)
    active_offers = Offer.objects.filter(author=actor.user, filled=False).order_by('-created_on')
    filled_offers = Offer.objects.filter(author=actor.user, filled=True).order_by('-created_on')
    return render(request, 'profiles/actor_detail.html', {
        'actor': actor, 'own': own,
        'troupe_profile': troupe_profile,
        'active_offers': active_offers,
        'filled_offers': filled_offers,
    })


@login_required
def actor_edit(request):
    profile = getattr(request.user, 'actor_profile', None)
    if request.method == 'POST':
        form = ActorProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            actor = form.save(commit=False)
            actor.user = request.user
            actor.save()
            _delete_actor_photos(actor, request.POST)
            _save_actor_photos(actor, request.FILES.getlist('extra_photos'))
            return redirect('profiles:actor_detail', slug=actor.slug)
    else:
        form = ActorProfileForm(instance=profile)
    return render(request, 'profiles/actor_edit.html', {
        'form': form,
        'profile': profile,
        'MAPBOX_ACCESS_TOKEN': os.environ.get('MAPBOX_ACCESS_TOKEN'),
    })


# ── Troupes ───────────────────────────────────────────────────────────────────

def troupe_detail(request, slug):
    troupe = get_object_or_404(TroupeProfile, slug=slug)
    own = request.user.is_authenticated and troupe.user == request.user
    actor_profile = getattr(troupe.user, 'actor_profile', None)
    active_offers = Offer.objects.filter(author=troupe.user, filled=False).order_by('-created_on')
    filled_offers = Offer.objects.filter(author=troupe.user, filled=True).order_by('-created_on')
    return render(request, 'profiles/troupe_detail.html', {
        'troupe': troupe, 'own': own,
        'actor_profile': actor_profile,
        'active_offers': active_offers,
        'filled_offers': filled_offers,
    })


@login_required
def troupe_edit(request):
    profile = getattr(request.user, 'troupe_profile', None)
    if request.method == 'POST':
        form = TroupeProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            troupe = form.save(commit=False)
            troupe.user = request.user
            troupe.save()
            _delete_troupe_photos(troupe, request.POST)
            _save_troupe_photos(troupe, request.FILES.getlist('extra_photos'))
            return redirect('profiles:troupe_detail', slug=troupe.slug)
    else:
        form = TroupeProfileForm(instance=profile)
    return render(request, 'profiles/troupe_edit.html', {
        'form': form,
        'profile': profile,
        'MAPBOX_ACCESS_TOKEN': os.environ.get('MAPBOX_ACCESS_TOKEN'),
    })


# ── Profil utilisateur global ──────────────────────────────────────────────────

def user_detail(request, pk):
    user = get_object_or_404(CustomUser, pk=pk)
    actor_profile = getattr(user, 'actor_profile', None)
    troupe_profile = getattr(user, 'troupe_profile', None)
    active_offers = Offer.objects.filter(author=user, filled=False).order_by('-created_on')
    filled_offers = Offer.objects.filter(author=user, filled=True).order_by('-created_on')
    plays = Play.objects.filter(user=user).order_by('-created_at')
    own = request.user.is_authenticated and request.user == user
    return render(request, 'profiles/user_detail.html', {
        'profile_user': user,
        'actor_profile': actor_profile,
        'troupe_profile': troupe_profile,
        'active_offers': active_offers,
        'filled_offers': filled_offers,
        'plays': plays,
        'own': own,
    })
