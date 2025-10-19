import os
from django.db.models import Q, Count, Min, Max, Subquery, OuterRef, Prefetch
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.utils.timezone import now
from django.http import HttpResponseForbidden, HttpResponse
from django.db import transaction
from django.utils import timezone
from datetime import datetime, time
from .models import Play, Representation, PublicationCredit
from .forms import RepresentationForm, PlayForm, ContributorFormSet, ContributorForm


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
    ).filter(user_id=request.user.id).prefetch_related(
        Prefetch(
            "representations",
            queryset=all_reps_qs.all(),
            to_attr="upcoming_representations"
        )
    ).order_by("next_datetime"))

    return render(request, "shows/agenda_user.html", {
        "plays": plays
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
    representations = play.representations.order_by('datetime')  # tri ascendant
    return render(request, "shows/play_detail.html", {"play": play, "representations": representations})



@login_required
def add_representation(request, pk):
    MAPBOX_ACCESS_TOKEN = os.environ.get("MAPBOX_ACCESS_TOKEN")
    play = get_object_or_404(Play, pk=pk, user=request.user)

    # --- Calcul du nombre de crédits par défaut ---
    today = timezone.now().date()
    total_plays = Play.objects.count()
    before_deadline = today <= timezone.datetime(year=2025, month=10, day=31).date()

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
        # instance Play "temp" pour binder le formset, on sauvegardera après
        play = Play(user=request.user)
        form = PlayForm(request.POST, request.FILES, instance=play)
        formset = ContributorFormSet(request.POST, prefix="contributors", instance=play)

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                play = form.save()  # déclenche ton save() -> poster compressé + nommage
                formset.instance = play
                formset.save()
            return redirect("shows:play_detail", pk=play.pk)
    else:
        form = PlayForm()
        # instance vide juste pour initialiser le formset
        play = Play()
        formset = ContributorFormSet(prefix="contributors", instance=play)

    return render(request, "shows/add_play.html", {
        "form": form, "formset": formset
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
        form = PlayForm(request.POST, request.FILES, instance=play)
        formset = ContributorFormSet(request.POST, prefix="contributors", instance=play)

        # gestion explicite de la suppression d'affiche si on garde un input custom
        poster_clear = request.POST.get("poster-clear") == "on"

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                play = form.save(commit=False)

                if poster_clear:
                    # supprime l'ancien fichier sans sauver tout de suite
                    if play.poster:
                        play.poster.delete(save=False)
                    play.poster = None  # et remet le champ à vide

                play.save()          # déclenche le save() avec pipeline image si nouveau fichier
                formset.instance = play
                formset.save()

            return redirect("shows:play_detail", pk=play.pk)
    else:
        form = PlayForm(instance=play)
        formset = ContributorFormSet(prefix="contributors", instance=play)

    return render(request, "shows/edit_play.html", {
        "form": form,
        "formset": formset,
        "play": play,
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