import os

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404

from accounts.models import CustomUser

from core.models import Alert, Offer
from shows.models import Play, PlayMembership

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
    active_offers = Offer.objects.filter(author=actor.user, filled=False, moderation_status=Offer.PUBLISHED).order_by('-created_on')
    filled_offers = Offer.objects.filter(author=actor.user, filled=True, moderation_status=Offer.PUBLISHED).order_by('-created_on')
    actor_plays = Play.objects.filter(
        memberships__user=actor.user, memberships__status=PlayMembership.STATUS_ACCEPTED
    ).order_by('-created_at')
    return render(request, 'profiles/actor_detail.html', {
        'actor': actor, 'own': own,
        'troupe_profile': troupe_profile,
        'active_offers': active_offers,
        'filled_offers': filled_offers,
        'actor_plays': actor_plays,
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
    active_offers = Offer.objects.filter(author=troupe.user, filled=False, moderation_status=Offer.PUBLISHED).order_by('-created_on')
    filled_offers = Offer.objects.filter(author=troupe.user, filled=True, moderation_status=Offer.PUBLISHED).order_by('-created_on')
    troupe_plays = Play.objects.filter(user=troupe.user).order_by('-created_at')
    return render(request, 'profiles/troupe_detail.html', {
        'troupe': troupe, 'own': own,
        'actor_profile': actor_profile,
        'active_offers': active_offers,
        'filled_offers': filled_offers,
        'troupe_plays': troupe_plays,
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


@login_required
def delete_actor_profile(request):
    profile = getattr(request.user, 'actor_profile', None)
    if request.method == 'POST' and profile:
        profile.delete()
    return redirect('profiles:user_detail', pk=request.user.pk)


@login_required
def delete_troupe_profile(request):
    profile = getattr(request.user, 'troupe_profile', None)
    if request.method == 'POST' and profile:
        profile.delete()
    return redirect('profiles:my_account')


# ── Mon espace ────────────────────────────────────────────────────────────────

@login_required
def my_account(request):
    from messaging.models import Conversation
    actor_profile = getattr(request.user, 'actor_profile', None)
    troupe_profile = getattr(request.user, 'troupe_profile', None)
    active_offers_count = Offer.objects.filter(author=request.user, filled=False).count()
    filled_offers_count = Offer.objects.filter(author=request.user, filled=True).count()
    plays_count = Play.objects.filter(user=request.user).count()
    actor_plays_count = PlayMembership.objects.filter(
        user=request.user, status=PlayMembership.STATUS_ACCEPTED
    ).exclude(play__user=request.user).count()
    conversations = Conversation.objects.filter(participants=request.user)
    conversations_count = conversations.count()
    unread_convs_count = sum(
        1 for c in conversations.prefetch_related('messages')
        if c.unread_count_for(request.user) > 0
    )
    unread_msgs_total = sum(
        c.unread_count_for(request.user)
        for c in conversations.prefetch_related('messages')
    )
    alerts_count = Alert.objects.filter(email=request.user.email, active=True).count()
    from promote.models import Promote
    from datetime import date as _date
    _today = _date.today()
    promotions_count = Promote.objects.filter(user=request.user, status='confirmed').count()
    active_promotions_count = Promote.objects.filter(
        user=request.user, status='confirmed',
        start_date__lte=_today, end_date__gte=_today,
    ).count()
    return render(request, 'profiles/my_account.html', {
        'actor_profile': actor_profile,
        'troupe_profile': troupe_profile,
        'active_offers_count': active_offers_count,
        'filled_offers_count': filled_offers_count,
        'plays_count': plays_count,
        'actor_plays_count': actor_plays_count,
        'conversations_count': conversations_count,
        'unread_convs_count': unread_convs_count,
        'unread_msgs_total': unread_msgs_total,
        'alerts_count': alerts_count,
        'promotions_count': promotions_count,
        'active_promotions_count': active_promotions_count,
    })


# ── Profil utilisateur global ──────────────────────────────────────────────────

def user_detail(request, pk):
    user = get_object_or_404(CustomUser, pk=pk)
    actor_profile = getattr(user, 'actor_profile', None)
    troupe_profile = getattr(user, 'troupe_profile', None)
    active_offers = Offer.objects.filter(author=user, filled=False, moderation_status=Offer.PUBLISHED).order_by('-created_on')
    filled_offers = Offer.objects.filter(author=user, filled=True, moderation_status=Offer.PUBLISHED).order_by('-created_on')
    created_plays = Play.objects.filter(user=user).order_by('-created_at')
    actor_plays = Play.objects.filter(
        memberships__user=user, memberships__status=PlayMembership.STATUS_ACCEPTED
    ).order_by('-created_at')
    own = request.user.is_authenticated and request.user == user
    return render(request, 'profiles/user_detail.html', {
        'profile_user': user,
        'actor_profile': actor_profile,
        'troupe_profile': troupe_profile,
        'active_offers': active_offers,
        'filled_offers': filled_offers,
        'created_plays': created_plays,
        'actor_plays': actor_plays,
        'own': own,
    })
