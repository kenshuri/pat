import os

from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404

from core.forms import OfferForm, SignUpForm
from core.models import Offer


# Create your views here.
def index(request):
    all_offers = Offer.objects.filter(filled=False).order_by('-created_on')
    return render(request, 'core/index.html', {'all_offers': all_offers})


def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            form.save()
            email = form.cleaned_data.get('email')
            raw_password = form.cleaned_data.get('password1')
            user = authenticate(email=email, password=raw_password)
            login(request, user)
            return redirect("index")
    else:
        form = SignUpForm()
    return render(request, 'registration/signup.html', {'form': form})


@login_required
def add_offer(request):
    MAPBOX_ACCESS_TOKEN = os.environ.get("MAPBOX_ACCESS_TOKEN")
    # with open('blogApp/static/fr_cities.json') as f:
    #     fr_cities = json.load(f)
    if request.method == 'POST':
        form = OfferForm(request.POST)
        if form.is_valid():
            offer = form.save(commit=False)
            # You can set additional fields here if needed
            # For example: offer.author = request.user
            offer.author = request.user
            offer.save()
            offer_id = offer.id
            return redirect('offer', offer_id=offer_id)
    else:
        form = OfferForm()
    return render(request,
                  'core/add_offer.html',
                  {'form': form, 'offer_id': -1, 'MAPBOX_ACCESS_TOKEN': MAPBOX_ACCESS_TOKEN})


@login_required
def update_offer(request, offer_id: int):
    MAPBOX_ACCESS_TOKEN = os.environ.get("MAPBOX_ACCESS_TOKEN")
    if request.method == 'POST':
        offer = get_object_or_404(Offer, id=offer_id)
        if offer.author != request.user:
            return redirect('offer', offer_id=offer_id)
        form = OfferForm(request.POST, instance=offer)
        if form.is_valid():
            form.save()
            return redirect('offer', offer_id=offer_id)
    else:
        offer = get_object_or_404(Offer, id=offer_id)
        if offer.author != request.user:
            return redirect('offer', offer_id=offer_id)
        form = OfferForm(instance=offer)
    return render(request,
                  'core/add_offer.html',
                  {'form': form, 'offer_id': offer_id, 'MAPBOX_ACCESS_TOKEN': MAPBOX_ACCESS_TOKEN})


@login_required
def delete_offer(request, offer_id: int):
    if request.user.id == Offer.objects.get(pk=offer_id).author.id:
        Offer.objects.get(pk=offer_id).delete()
        return redirect('index')
    else:
        return redirect('index')


@login_required
def fill_offer(request, offer_id: int):
    if request.user.id == Offer.objects.get(pk=offer_id).author.id:
        offer = get_object_or_404(Offer, pk=offer_id)
        offer.filled = True
        offer.save()
        return redirect('offer', offer_id=offer_id)
    else:
        return redirect('offer', offer_id=offer_id)


@login_required
def unfill_offer(request, offer_id: int):
    if request.user.id == Offer.objects.get(pk=offer_id).author.id:
        offer = get_object_or_404(Offer, pk=offer_id)
        offer.filled = False
        offer.save()
        return redirect('offer', offer_id=offer_id)
    else:
        return redirect('offer', offer_id=offer_id)



def offer(request, offer_id: int):
    offer = get_object_or_404(Offer, pk=offer_id)
    return render(request, 'core/offer.html', {'offer': offer})


def offer_search(request):
    search_query = request.POST.get('search')
    if search_query:
        results = Offer.objects.filter(filled=False).filter(title__icontains=search_query) | Offer.objects.filter(filled=False).filter(summary__icontains=search_query) | Offer.objects.filter(city__icontains=search_query)
    else:
        # If no query is provided, return all books
        results = Offer.objects.filter(filled=False)

    context = {
        'all_offers': results.order_by('-created_on')
    }

    return render(request, 'core/partials/offers_partials.html', context)


@login_required
def offer_user(request):
    user_offers = Offer.objects.filter(author=request.user.id)
    context = {
        'all_offers': user_offers.order_by('-created_on')
    }
    return render(request, 'core/offer_user.html', context)



def offer_contact_info(request, offer_id: int):
    offer = get_object_or_404(Offer, pk=offer_id)
    return render(request, 'core/partials/offer_contact_info.html', {'offer': offer})


def about(request):
    return render(request, 'core/about.html')


def tou(request):
    return render(request, 'core/tou.html')

def announcement(request):
    return render(request, 'core/announcement.html')


