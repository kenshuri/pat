import logging
import os

from django.conf import settings
from django.contrib import messages as django_messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q, Count, Min, Max, Subquery, OuterRef, Prefetch
from django.http import HttpResponseForbidden, HttpResponse, Http404
from django.shortcuts import get_object_or_404, render, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.timezone import now
from datetime import datetime, time

from accounts.models import CustomUser
from .models import Play, PlayMembership, PlayPhoto, Representation, PublicationCredit, _process_image
from .forms import RepresentationForm, PlayForm, ContributorFormSet, ContributorForm
from core.tasks import moderate_play

logger = logging.getLogger(__name__)


def _save_play_extra_photos(play, files):
    existing_count = play.photos.count()
    for i, file in enumerate(files):
        photo = PlayPhoto(play=play, order=existing_count + i)
        photo.save()
        photo.image = file
        _process_image(photo.image, "photo.webp")
        photo.save(update_fields=['image'])


def _delete_play_extra_photos(play, post_data):
    for key in post_data:
        if key.startswith('delete_photo_'):
            pk = key.removeprefix('delete_photo_')
            play.photos.filter(pk=pk).delete()


def agenda(request):
    now_ts = now()

    # Sous-requête pour ticket_url uniquement
    future_rep_subquery = Representation.objects.filter(
        datetime__gte=now_ts,
        play=OuterRef("pk")
    ).order_by("datetime")

    # QuerySet utilisable dans prefetch_related
    future_reps_qs = Representation.objects.filter(datetime__gte=now_ts).order_by("datetime")

    plays = Play.objects.annotate(
        next_datetime=Min("representations__datetime", filter=Q(representations__datetime__gte=now_ts)),
        last_datetime=Max("representations__datetime", filter=Q(representations__datetime__gte=now_ts)),
        representation_count=Count("representations", filter=Q(representations__datetime__gte=now_ts)),
        ticket_url=Subquery(future_rep_subquery.values("ticket_url")[:1])
    ).filter(
        next_datetime__isnull=False
    ).prefetch_related(
        Prefetch(
            "representations",
            queryset=future_reps_qs.all(),
            to_attr="upcoming_representations"
        )
    ).order_by("next_datetime", "created_at")

    return render(request, "shows/agenda.html", {
        "plays": plays
    })

def agenda_user(request):
    all_reps_qs = Representation.objects.order_by("datetime")

    def _annotated_plays(qs):
        return qs.annotate(
            next_datetime=Min("representations__datetime"),
            last_datetime=Max("representations__datetime"),
            representation_count=Count("representations"),
        ).prefetch_related(
            Prefetch("representations", queryset=all_reps_qs.all(), to_attr="upcoming_representations")
        ).order_by("next_datetime")

    created_plays = _annotated_plays(Play.objects.filter(user=request.user))

    actor_plays = _annotated_plays(
        Play.objects.filter(
            memberships__user=request.user,
            memberships__status=PlayMembership.STATUS_ACCEPTED,
        ).exclude(user=request.user)
    )

    pending_requests = (
        PlayMembership.objects
        .filter(direction=PlayMembership.DIRECTION_REQUEST, status=PlayMembership.STATUS_PENDING, play__user=request.user)
        .select_related('play', 'user', 'initiated_by')
        .order_by('created_at')
    )

    pending_invitations = (
        PlayMembership.objects
        .filter(direction=PlayMembership.DIRECTION_INVITE, status=PlayMembership.STATUS_PENDING, user=request.user)
        .select_related('play', 'play__user')
        .order_by('created_at')
    )

    return render(request, "shows/agenda_user.html", {
        "created_plays": created_plays,
        "actor_plays": actor_plays,
        "pending_requests": pending_requests,
        "pending_invitations": pending_invitations,
    })

def agenda_filter(request):
    query = request.GET.get("search", "").strip()
    genre = request.GET.get("genre", "").strip()
    date_from_str = request.GET.get("date_from", "").strip()
    date_to_str = request.GET.get("date_to", "").strip()

    # Helpers TZ
    tz = timezone.get_current_timezone()

    def aware_day_bounds(d):
        start = timezone.make_aware(datetime.combine(d, time.min), tz)
        end = timezone.make_aware(datetime.combine(d, time.max), tz)
        return start, end

    # Parse dates (YYYY-MM-DD)
    date_from, date_to = None, None
    if date_from_str:
        try:
            d = datetime.strptime(date_from_str, "%Y-%m-%d").date()
            date_from, _ = aware_day_bounds(d)  # début de journée
        except ValueError:
            pass
    if date_to_str:
        try:
            d = datetime.strptime(date_to_str, "%Y-%m-%d").date()
            _, date_to = aware_day_bounds(d)    # fin de journée
        except ValueError:
            pass

    # Base: on part de TOUT, puis on applique la logique de dates
    representations_qs = Representation.objects.all().order_by("datetime")

    # --- LOGIQUE DE DATES DEMANDÉE ---
    if not date_from and not date_to:
        # Comportement par défaut (futur)
        representations_qs = representations_qs.filter(datetime__gte=timezone.now())

    elif not date_from and date_to:
        # Seulement date_to : aujourd'hui 00:00 -> date_to 23:59:59
        today = timezone.localdate()
        today_start, _ = aware_day_bounds(today)
        representations_qs = representations_qs.filter(datetime__range=(today_start, date_to))

    elif date_from and not date_to:
        # Seulement date_from : à partir de date_from 00:00
        representations_qs = representations_qs.filter(datetime__gte=date_from)

    else:
        # Deux bornes : intervalle inclusif
        # Si l'utilisateur a inversé, on swap par sécurité
        if date_to < date_from:
            date_from, date_to = date_to, date_from
        representations_qs = representations_qs.filter(datetime__range=(date_from, date_to))

    # --- Autres filtres ---
    if query:
        representations_qs = representations_qs.filter(
            Q(play__title__icontains=query) |
            Q(city__icontains=query) |
            Q(venue__icontains=query)
        )
    if genre:
        representations_qs = representations_qs.filter(play__genre=genre)

    # --- Agrégations Plays basées sur le sous-ensemble filtré ---
    future_reps = representations_qs.filter(play=OuterRef("pk")).order_by("datetime")

    plays = Play.objects.annotate(
        next_datetime=Min("representations__datetime", filter=Q(representations__in=representations_qs)),
        last_datetime=Max("representations__datetime", filter=Q(representations__in=representations_qs)),
        representation_count=Count("representations", filter=Q(representations__in=representations_qs)),
        ticket_url=Subquery(future_reps.values("ticket_url")[:1]),
    ).filter(
        next_datetime__isnull=False
    ).prefetch_related(
        Prefetch("representations", queryset=representations_qs, to_attr="upcoming_representations")
    ).order_by("next_datetime")

    return render(request, "shows/partials/plays_table.html", {"plays": plays})


def play_detail(request, pk):
    play = get_object_or_404(Play, pk=pk)
    if play.moderation_status != Play.PUBLISHED:
        if not request.user.is_authenticated or request.user != play.user:
            raise Http404
    representations = play.representations.order_by('datetime')
    troupe_profile = getattr(play.user, 'troupe_profile', None) if play.user else None
    accepted_members = (
        PlayMembership.objects
        .filter(play=play, status=PlayMembership.STATUS_ACCEPTED)
        .select_related('user', 'user__actor_profile', 'user__troupe_profile')
        .order_by('created_at')
    )
    user_membership = None
    if request.user.is_authenticated:
        user_membership = PlayMembership.objects.filter(play=play, email=request.user.email).first()
    return render(request, "shows/play_detail.html", {
        "play": play,
        "representations": representations,
        "troupe_profile": troupe_profile,
        "accepted_members": accepted_members,
        "user_membership": user_membership,
    })


@login_required
def play_owner_zone(request, pk):
    play = get_object_or_404(Play, pk=pk, user=request.user)
    return render(request, "shows/partials/play_owner_zone.html", {"play": play})


@login_required
def add_representation(request, pk):
    MAPBOX_ACCESS_TOKEN = os.environ.get("MAPBOX_ACCESS_TOKEN")
    play = get_object_or_404(Play, pk=pk, user=request.user)

    # --- Calcul du nombre de crédits par défaut ---
    today = timezone.now().date()
    total_plays = Play.objects.count()
    before_deadline = today <= timezone.datetime(year=2025, month=12, day=31).date()

    default_credits = 6 if total_plays < 25 or before_deadline else 0

    # 1) S'assurer que l'objet crédit existe, sinon le créer à 0
    credit, _ = PublicationCredit.objects.get_or_create(
        user=request.user, defaults={"remaining_credits": default_credits}
    )

    if request.method == "POST":
        form = RepresentationForm(request.POST)
        if form.is_valid():
            rep = form.save(commit=False)
            rep.play = play
            rep.save()

            # Décrémente les crédits de publication de l'utilisateur
            credit = request.user.publication_credit
            if credit.remaining_credits > 0:
                credit.remaining_credits -= 1
                credit.save()

            return render(request, "shows/partials/representation_row.html", {"rep": rep})
    else:
        form = RepresentationForm()

    return render(request, "shows/partials/representation_form.html", {
        "form": form,
        "play": play,
        'MAPBOX_ACCESS_TOKEN': MAPBOX_ACCESS_TOKEN
    })


@login_required
def get_remaining_credits(request):
    credits = request.user.publication_credit.remaining_credits
    return HttpResponse(f"Crédits restants : {credits}")

@login_required
def get_representation_form_partial_credit(request):
    return render(request, "shows/partials/representation_form_partial_credit.html", {})


@login_required
def delete_representation(request, pk):
    rep = get_object_or_404(Representation, pk=pk)
    if rep.play.user != request.user:
        return HttpResponseForbidden("Vous n’avez pas la permission de supprimer cette représentation.")

    rep.delete()

    # If the request is made via HTMX, return a 204 to remove the row
    if request.headers.get("Hx-Request") == "true":
        return HttpResponse("")

    # Fallback if needed
    return redirect("shows:play_detail", pk=rep.play.pk)

@login_required
def add_play(request):
    if request.method == "POST":
        play = Play(user=request.user)
        form = PlayForm(request.POST, request.FILES, instance=play)
        formset = ContributorFormSet(request.POST, prefix="contributors", instance=play)

        if form.is_valid() and formset.is_valid():
            title = form.cleaned_data.get('title', '')
            ten_seconds_ago = timezone.now() - timezone.timedelta(seconds=10)
            if Play.objects.filter(user=request.user, title=title, created_at__gte=ten_seconds_ago).exists():
                return redirect("shows:play_list")
            with transaction.atomic():
                play = form.save()
                formset.instance = play
                formset.save()
            _save_play_extra_photos(play, request.FILES.getlist('extra_photos'))
            _process_invitations(request, play)
            moderate_play.delay(play.pk)
            return redirect("shows:play_detail", pk=play.pk)
    else:
        form = PlayForm()
        play = Play()
        formset = ContributorFormSet(prefix="contributors", instance=play)

    return render(request, "shows/add_play.html", {
        "form": form, "formset": formset, "play_id": -1,
    })

@login_required
def contributor_empty_row(request):
    """
    Retourne une ligne vierge de contribution pour HTMX,
    avec le prefix 'contributors-<index>'.
    """
    if not request.headers.get("HX-Request"):
        return HttpResponseForbidden("HTMX only")

    try:
        index = int(request.GET.get("index", "0"))
    except ValueError:
        index = 0

    form = ContributorForm(prefix=f"contributors-{index}")
    return render(request, "shows/partials/contributor_row.html", {"form": form, "index": index})


@login_required
def edit_play(request, pk):
    play = get_object_or_404(Play, pk=pk)
    if play.user != request.user:
        return HttpResponseForbidden("Vous n’avez pas la permission de modifier cette pièce.")

    if request.method == "POST":
        old_title = play.title
        old_desc = play.description
        old_poster_name = play.poster.name if play.poster else None
        old_cover_name = play.cover_image.name if play.cover_image else None
        form = PlayForm(request.POST, request.FILES, instance=play)
        formset = ContributorFormSet(request.POST, prefix="contributors", instance=play)

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                play = form.save(commit=False)
                if request.POST.get("poster-clear") == "on" and play.poster:
                    play.poster.delete(save=False)
                    play.poster = None
                if request.POST.get("cover-clear") == "on" and play.cover_image:
                    play.cover_image.delete(save=False)
                    play.cover_image = None
                play.save()
                formset.instance = play
                formset.save()

            _delete_play_extra_photos(play, request.POST)
            _save_play_extra_photos(play, request.FILES.getlist('extra_photos'))
            _process_invitations(request, play)
            _update_membership_roles(request, play)
            moderated_changed = (
                play.title != old_title
                or play.description != old_desc
                or (play.poster.name if play.poster else None) != old_poster_name
                or (play.cover_image.name if play.cover_image else None) != old_cover_name
                or 'poster' in request.FILES
                or 'cover_image' in request.FILES
                or request.POST.get("poster-clear") == "on"
                or request.POST.get("cover-clear") == "on"
                or bool(request.FILES.getlist('extra_photos'))
                or any(k.startswith('delete_photo_') for k in request.POST)
            )
            if moderated_changed:
                play.moderation_status = Play.PENDING
                play.save(update_fields=['moderation_status'])
                moderate_play.delay(play.pk)
            return redirect("shows:play_detail", pk=play.pk)
    else:
        form = PlayForm(instance=play)
        formset = ContributorFormSet(prefix="contributors", instance=play)

    accepted_members = play.memberships.filter(
        status=PlayMembership.STATUS_ACCEPTED
    ).select_related('user__actor_profile')
    pending_invitations = play.memberships.filter(
        status=PlayMembership.STATUS_PENDING,
        direction=PlayMembership.DIRECTION_INVITE,
    ).select_related('user__actor_profile')
    user_actor_profile = getattr(request.user, 'actor_profile', None)
    user_in_cast = play.memberships.filter(
        user=request.user, status=PlayMembership.STATUS_ACCEPTED
    ).exists()
    return render(request, "shows/edit_play.html", {
        "form": form,
        "formset": formset,
        "play": play,
        "play_id": play.pk,
        "accepted_members": accepted_members,
        "pending_invitations": pending_invitations,
        "user_actor_profile": user_actor_profile,
        "user_in_cast": user_in_cast,
    })


@login_required
def delete_play(request, pk):
    play = get_object_or_404(Play, pk=pk)

    # Autorisation : seul le propriétaire peut supprimer
    if play.user_id != request.user.id:
        return HttpResponseForbidden("Vous n’avez pas la permission de supprimer cette pièce.")

    if request.method == "POST":
        # Supprime le fichier d'affiche du storage (si présent) SANS déclencher save()
        if play.poster:
            play.poster.delete(save=False)

        # Supprime l'objet Play (les Contributors et Representations partiront en cascade)
        play.delete()

        # Si requête HTMX : on peut renvoyer un 204 (contenu vide)
        if request.headers.get("Hx-Request") == "true":
            return HttpResponse(status=204)

        # Sinon, redirection vers l'agenda utilisateur (ajuste si besoin)
        return redirect("shows:agenda-user")

    # GET -> page de confirmation
    return render(request, "shows/confirm_delete_play.html", {"play": play})


def _display_name(user):
    if user is None:
        return 'Un utilisateur'
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


def _send_play_invite(request, membership, is_registered):
    template = 'emails/play_invite_registered.html' if is_registered else 'emails/play_invite_unregistered.html'
    play = membership.play
    initiator = membership.initiated_by
    accept_url = request.build_absolute_uri(f'/shows/membership/{membership.token}/accept/')
    decline_url = request.build_absolute_uri(f'/shows/membership/{membership.token}/decline/')
    play_url = request.build_absolute_uri(f'/shows/play/{play.pk}/')
    context = {
        'play': play,
        'play_url': play_url,
        'initiator_name': _display_name(initiator),
        'initiator_profile_url': request.build_absolute_uri(f'/membre/{initiator.pk}/') if initiator else '',
        'role': membership.role,
        'accept_url': accept_url,
        'decline_url': decline_url,
        'site_url': settings.SITE_URL,
    }
    html_body = render_to_string(template, context)
    text_body = (
        f'{_display_name(initiator)} vous invite à rejoindre la pièce "{play.title}".\n\n'
        f'Accepter : {accept_url}\nRefuser : {decline_url}\n\n— Petites Annonces Théâtre'
    )
    try:
        send_mail(
            f'Invitation à rejoindre "{play.title}"',
            text_body,
            settings.DEFAULT_FROM_EMAIL,
            [membership.email],
            html_message=html_body,
            fail_silently=False,
        )
    except Exception as e:
        logger.error('Échec envoi invitation pièce #%s à %s : %s', play.pk, membership.email, e)


def _send_join_request(request, membership):
    play = membership.play
    requester = membership.initiated_by
    accept_url = request.build_absolute_uri(f'/shows/membership/{membership.token}/accept/')
    decline_url = request.build_absolute_uri(f'/shows/membership/{membership.token}/decline/')
    owner = play.user
    if not owner or not owner.email:
        return
    context = {
        'play': play,
        'requester_name': _display_name(requester),
        'requester_profile_url': request.build_absolute_uri(f'/membre/{requester.pk}/') if requester else '',
        'requester': requester,
        'accept_url': accept_url,
        'decline_url': decline_url,
        'site_url': settings.SITE_URL,
    }
    html_body = render_to_string('emails/play_join_request.html', context)
    text_body = (
        f'{_display_name(requester)} demande à rejoindre votre pièce "{play.title}".\n\n'
        f'Accepter : {accept_url}\nRefuser : {decline_url}\n\n— Petites Annonces Théâtre'
    )
    try:
        send_mail(
            f'Demande de participation à "{play.title}"',
            text_body,
            settings.DEFAULT_FROM_EMAIL,
            [owner.email],
            html_message=html_body,
            fail_silently=False,
        )
    except Exception as e:
        logger.error('Échec envoi demande participation pièce #%s : %s', play.pk, e)


def _update_membership_roles(request, play):
    prefix = 'member_role_'
    updates = {k[len(prefix):]: v.strip() for k, v in request.POST.items() if k.startswith(prefix)}
    if updates:
        import uuid as _uuid
        for token_str, role in updates.items():
            try:
                token = _uuid.UUID(token_str)
            except ValueError:
                continue
            play.memberships.filter(token=token).update(role=role)


def _process_invitations(request, play):
    """Parse invite_email_N / invite_role_N from POST and create PlayMembership entries."""
    i = 0
    while True:
        email = request.POST.get(f'invite_email_{i}', '').strip().lower()
        if not email:
            break
        role = request.POST.get(f'invite_role_{i}', '').strip()
        i += 1
        if PlayMembership.objects.filter(play=play, email=email).exists():
            continue
        user = CustomUser.objects.filter(email=email).first()
        m = PlayMembership.objects.create(
            play=play,
            email=email,
            user=user,
            role=role,
            direction=PlayMembership.DIRECTION_INVITE,
            initiated_by=request.user,
        )
        _send_play_invite(request, m, is_registered=user is not None)


@login_required
def add_self_to_cast(request, pk):
    play = get_object_or_404(Play, pk=pk, user=request.user)
    if request.method == 'POST':
        m, created = PlayMembership.objects.get_or_create(
            play=play,
            email=request.user.email,
            defaults={
                'user': request.user,
                'direction': PlayMembership.DIRECTION_INVITE,
                'status': PlayMembership.STATUS_ACCEPTED,
                'initiated_by': request.user,
            },
        )
        if not created and m.status != PlayMembership.STATUS_ACCEPTED:
            m.status = PlayMembership.STATUS_ACCEPTED
            m.save()
        if request.headers.get('HX-Request'):
            from django.http import HttpResponse as HR
            r = HR()
            r['HX-Refresh'] = 'true'
            return r
    return redirect('shows:play_detail', pk=pk)


@login_required
def delete_membership(request, token):
    m = get_object_or_404(PlayMembership, token=token, play__user=request.user)
    play_pk = m.play.pk
    if request.method == 'POST':
        m.delete()
        if request.headers.get('HX-Request'):
            from django.http import HttpResponse as HR
            r = HR()
            r['HX-Refresh'] = 'true'
            return r
    return redirect('shows:edit_play', pk=play_pk)


@login_required
def request_join(request, pk):
    play = get_object_or_404(Play, pk=pk)
    if play.user == request.user:
        return redirect('shows:play_detail', pk=pk)
    if request.method == 'POST':
        existing = PlayMembership.objects.filter(play=play, email=request.user.email).first()
        if existing:
            if existing.status == PlayMembership.STATUS_DECLINED:
                django_messages.info(request, 'Votre demande a déjà été refusée.')
            else:
                django_messages.info(request, 'Vous avez déjà une demande en cours ou êtes déjà membre.')
        else:
            m = PlayMembership.objects.create(
                play=play,
                email=request.user.email,
                user=request.user,
                direction=PlayMembership.DIRECTION_REQUEST,
                initiated_by=request.user,
            )
            _send_join_request(request, m)
            django_messages.success(request, 'Votre demande a été envoyée au créateur de la pièce.')
    return redirect('shows:play_detail', pk=pk)


@login_required
def cancel_invitation(request, token):
    m = get_object_or_404(PlayMembership, token=token, play__user=request.user,
                          direction=PlayMembership.DIRECTION_INVITE, status=PlayMembership.STATUS_PENDING)
    if request.method == 'POST':
        m.status = PlayMembership.STATUS_CANCELLED
        m.save()
        if request.headers.get('HX-Request'):
            from django.http import HttpResponse as HR
            r = HR()
            r['HX-Refresh'] = 'true'
            return r
    return redirect('shows:edit_play', pk=m.play.pk)


def membership_respond(request, token, action):
    m = get_object_or_404(PlayMembership, token=token)
    if m.status == PlayMembership.STATUS_CANCELLED:
        django_messages.warning(request, 'Cette invitation a été annulée par le créateur de la pièce.')
        return redirect('shows:play_detail', pk=m.play.pk)
    if m.status != PlayMembership.STATUS_PENDING:
        django_messages.info(request, 'Cette invitation a déjà été traitée.')
        return redirect('shows:play_detail', pk=m.play.pk)
    next_url = request.GET.get('next', '')
    if action == 'accept':
        m.status = PlayMembership.STATUS_ACCEPTED
        m.save()
        if m.direction == PlayMembership.DIRECTION_INVITE and m.user is None:
            django_messages.success(request, f'Vous avez rejoint "{m.play.title}". Créez un compte pour compléter votre profil !')
            return redirect(f'/accounts/signup/?next=/shows/play/{m.play.pk}/')
        django_messages.success(request, f'Vous avez rejoint "{m.play.title}".')
    elif action == 'decline':
        m.status = PlayMembership.STATUS_DECLINED
        m.save()
        django_messages.info(request, 'Vous avez refusé cette invitation.')
    else:
        return HttpResponse(status=400)
    if next_url and next_url.startswith('/'):
        return redirect(next_url)
    return redirect('shows:play_detail', pk=m.play.pk)


def repertoire(request):
    """
    Affiche toutes les pièces, avec ou sans représentations,
    triées par date d’ajout (les plus récentes d’abord).
    """
    # Sous-requête pour ticket_url uniquement
    all_rep_subquery = Representation.objects.filter(
        play=OuterRef("pk")
    ).order_by("datetime")

    # QuerySet utilisable dans prefetch_related
    all_reps_qs = Representation.objects.order_by("datetime")

    plays = (Play.objects.annotate(
        next_datetime=Min("representations__datetime"),
        last_datetime=Max("representations__datetime"),
        representation_count=Count("representations"),
    ).prefetch_related(
        Prefetch(
            "representations",
            queryset=all_reps_qs.all(),
            to_attr="upcoming_representations"
        )
    ).order_by("-created_at"))

    return render(request, "shows/repertoire.html", {"plays": plays})