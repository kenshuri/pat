import logging

from django.contrib import messages as django_messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)

from core.models import Offer
from .forms import MessageForm, ReportForm
from .models import Conversation, Message
from .moderation import get_flag_reason


def _sender_display_name(user):
    if user is None:
        return 'Utilisateur supprimé'
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
    return 'un utilisateur'


def _user_profile_url(request, user):
    if user is None:
        return ''
    try:
        from django.urls import reverse
        return request.build_absolute_uri(
            reverse('profiles:user_detail', kwargs={'pk': user.pk})
        )
    except Exception:
        return ''


def _send_report_notification(request, msg, reason, *, auto_label=None):
    """Notifie les admins d'un message signalé.

    Mode manuel (défaut) : signalé par request.user.
    Mode auto (auto_label fourni) : flaggé par la détection regex.
    """
    auto = auto_label is not None
    conv = msg.conversation
    admin_emails = [email for _, email in settings.ADMINS]
    if not admin_emails:
        return

    offer = conv.offer
    site_url = settings.SITE_URL

    # Enrichit chaque message avec son sender_display pour le template
    all_messages = list(conv.messages.select_related('sender').all())
    for m in all_messages:
        m.sender_display = _sender_display_name(m.sender) if m.sender else 'Utilisateur supprimé'

    context = {
        'is_auto': auto,
        'reporter_name': 'Détection automatique' if auto else _sender_display_name(request.user),
        'reporter_email': '' if auto else request.user.email,
        'reporter_profile_url': '' if auto else _user_profile_url(request, request.user),
        'sender_name': _sender_display_name(msg.sender),
        'sender_email': msg.sender.email if msg.sender else '—',
        'flag_reason': reason,
        'offer_title': offer.title if offer else '—',
        'offer_url': request.build_absolute_uri(f'/offer/{offer.pk}') if offer else '',
        'sender_profile_url': _user_profile_url(request, msg.sender),
        'admin_url': f'{site_url}/admin/messaging/message/{msg.pk}/change/',
        'site_url': site_url,
        'messages': all_messages,
        'reported_message_pk': msg.pk,
    }

    html_body = render_to_string('emails/report_notification.html', context)
    if auto:
        subject = f'[PAT] 🤖 Détection auto — {auto_label} — {context["offer_title"]}'
        text_body = (
            f'Message flaggé automatiquement #{msg.pk}\n'
            f'Détection : {auto_label}\n'
            f'Auteur : {context["sender_name"]} ({context["sender_email"]})\n'
            f'Raison : {reason}\n'
            f'Annonce : {context["offer_title"]}\n\n'
            f'Contenu :\n{msg.body}'
        )
    else:
        subject = f'[PAT] 🚩 Message signalé — {context["offer_title"]}'
        text_body = (
            f'Message signalé #{msg.pk}\n'
            f'Signalé par : {context["reporter_name"]}\n'
            f'Auteur : {context["sender_name"]}\n'
            f'Raison : {reason or "Non précisée"}\n'
            f'Annonce : {context["offer_title"]}\n\n'
            f'Contenu :\n{msg.body}'
        )
    try:
        send_mail(
            subject,
            text_body,
            settings.DEFAULT_FROM_EMAIL,
            admin_emails,
            html_message=html_body,
            fail_silently=False,
        )
    except Exception as e:
        logger.error('Échec envoi notification signalement (msg #%s) : %s', msg.pk, e)


def _send_reveal_notification(request, conv, shared_info, recipient):
    if not recipient or not recipient.email:
        return
    offer_title = conv.offer.title if conv.offer else 'une annonce'
    sender_name = _sender_display_name(conv.get_other_participant(recipient))
    conv_url = request.build_absolute_uri(f'/messages/{conv.pk}/')
    recipient_display = _sender_display_name(recipient)
    subject = f'Nouvelles coordonnées partagées — {offer_title}'
    html_body = render_to_string('emails/reveal_notification.html', {
        'recipient_name': None if recipient_display == 'un utilisateur' else recipient_display,
        'sender_name': sender_name,
        'offer_title': offer_title,
        'conv_url': conv_url,
    })
    text_body = (
        f'Bonjour,\n\n{sender_name} a partagé ses coordonnées avec vous '
        f'dans la conversation concernant "{offer_title}".\n\n'
        f'Consultez la conversation : {conv_url}\n\n'
        '— Petites Annonces Théâtre'
    )
    try:
        send_mail(subject, text_body, settings.DEFAULT_FROM_EMAIL, [recipient.email],
                  html_message=html_body, fail_silently=False)
    except Exception as e:
        logger.error('Échec envoi notification partage coordonnées (conv #%s) : %s', conv.pk, e)


def _send_notification(request, conv, msg, recipient):
    if not recipient or not recipient.email:
        return
    offer_title = conv.offer.title if conv.offer else 'une annonce'
    sender_name = _sender_display_name(msg.sender)
    subject = f'Nouveau message concernant votre annonce "{offer_title}"'
    conv_url = request.build_absolute_uri(f'/messages/{conv.pk}/')
    recipient_display = _sender_display_name(recipient)
    html_body = render_to_string('emails/message_notification.html', {
        'recipient_name': None if recipient_display == 'un utilisateur' else recipient_display,
        'sender_name': sender_name,
        'offer_title': offer_title,
        'conv_url': conv_url,
    })
    text_body = (
        f'Bonjour,\n\n{sender_name} vous a envoyé un message concernant '
        f'l\'annonce "{offer_title}".\n\n'
        f'Consultez votre messagerie : {conv_url}\n\n'
        '— Petites Annonces Théâtre'
    )
    try:
        send_mail(
            subject,
            text_body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient.email],
            html_message=html_body,
            fail_silently=False,
        )
    except Exception as e:
        logger.error('Échec envoi notification message (conv #%s) : %s', conv.pk, e)


def _apply_moderation(msg, body):
    """Flagge le message si suspect. Retourne (label, extrait) ou None."""
    reason = get_flag_reason(body)
    if reason:
        label, snippet = reason
        msg.is_flagged = True
        msg.flag_reason = f'Détection automatique — {label} : {snippet}'
    return reason


def _rate_limit_exceeded(user):
    one_hour_ago = timezone.now() - timezone.timedelta(hours=1)
    return Message.objects.filter(sender=user, sent_at__gte=one_hour_ago).count() >= 10


def _is_duplicate(user, conversation, body):
    five_seconds_ago = timezone.now() - timezone.timedelta(seconds=5)
    return Message.objects.filter(
        sender=user,
        conversation=conversation,
        body=body,
        sent_at__gte=five_seconds_ago,
    ).exists()


@login_required
def inbox(request):
    conversations = (
        Conversation.objects
        .filter(participants=request.user)
        .prefetch_related('participants', 'messages')
        .select_related('offer')
    )
    conv_data = []
    for conv in conversations:
        other = conv.get_other_participant(request.user)
        last = conv.last_message()
        unread = conv.unread_count_for(request.user)
        conv_data.append({'conv': conv, 'other': other, 'last': last, 'unread': unread})
    return render(request, 'messaging/inbox.html', {'conv_data': conv_data})


@login_required
def conversation_detail(request, pk):
    conv = get_object_or_404(Conversation, pk=pk, participants=request.user)
    conv.messages.filter(read_at__isnull=True).exclude(sender=request.user).update(read_at=timezone.now())
    other = conv.get_other_participant(request.user)

    user_sent = conv.messages.filter(sender=request.user, is_system=False).exists()
    other_sent = other and conv.messages.filter(sender=other, is_system=False).exists()
    can_reveal = user_sent and other_sent
    already_revealed = conv.messages.filter(sender=request.user, is_system=True).exists()

    if request.method == 'POST':
        form = MessageForm(request.POST)
        if form.is_valid():
            if _rate_limit_exceeded(request.user):
                django_messages.error(
                    request,
                    'Vous avez atteint la limite de 10 messages par heure. Réessayez plus tard.'
                )
                return redirect('messaging:conversation', pk=pk)
            body = form.cleaned_data['body']
            if _is_duplicate(request.user, conv, body):
                return redirect('messaging:conversation', pk=pk)
            msg = Message(conversation=conv, sender=request.user, body=body)
            flag = _apply_moderation(msg, body)
            msg.save()
            conv.save()
            if flag:
                _send_report_notification(request, msg, msg.flag_reason, auto_label=flag[0])
            if other:
                _send_notification(request, conv, msg, other)
            return redirect('messaging:conversation', pk=pk)
    else:
        form = MessageForm()

    return render(request, 'messaging/conversation.html', {
        'conv': conv,
        'other': other,
        'form': form,
        'can_reveal': can_reveal,
        'already_revealed': already_revealed,
    })


@login_required
def new_conversation(request, offer_id):
    offer = get_object_or_404(Offer, pk=offer_id, allow_messaging=True)

    if offer.author == request.user:
        django_messages.error(request, 'Vous ne pouvez pas vous envoyer un message à vous-même.')
        return redirect('offer', offer_id=offer_id)

    if offer.author:
        existing = (
            Conversation.objects
            .filter(offer=offer, participants=request.user)
            .filter(participants=offer.author)
            .first()
        )
        if existing:
            return redirect('messaging:conversation', pk=existing.pk)

    if request.method == 'POST':
        form = MessageForm(request.POST)
        if form.is_valid():
            if _rate_limit_exceeded(request.user):
                django_messages.error(request, 'Vous avez atteint la limite de 10 messages par heure.')
                return redirect('offer', offer_id=offer_id)
            body = form.cleaned_data['body']
            conv = Conversation.objects.create(offer=offer, offer_title=offer.title)
            conv.participants.add(request.user)
            if offer.author:
                conv.participants.add(offer.author)
            msg = Message(conversation=conv, sender=request.user, body=body)
            flag = _apply_moderation(msg, body)
            msg.save()
            if flag:
                _send_report_notification(request, msg, msg.flag_reason, auto_label=flag[0])
            if offer.author:
                _send_notification(request, conv, msg, offer.author)
            return redirect('messaging:conversation', pk=conv.pk)
    else:
        form = MessageForm()

    return render(request, 'messaging/new_conversation.html', {'offer': offer, 'form': form})


@login_required
def report_message(request, message_id):
    msg = get_object_or_404(Message, pk=message_id)

    if not msg.conversation.participants.filter(pk=request.user.pk).exists():
        django_messages.error(request, 'Action non autorisée.')
        return redirect('messaging:inbox')

    if msg.sender == request.user:
        django_messages.error(request, 'Vous ne pouvez pas signaler votre propre message.')
        return redirect('messaging:conversation', pk=msg.conversation.pk)

    if request.method == 'POST':
        form = ReportForm(request.POST)
        if form.is_valid():
            reason = form.cleaned_data.get('reason', '')
            msg.is_flagged = True
            msg.flag_reason = f'Signalement manuel — {reason}' if reason else 'Signalement manuel'
            msg.save()
            _send_report_notification(request, msg, reason)
            django_messages.success(request, 'Le message a été signalé. Merci.')
            return redirect('messaging:conversation', pk=msg.conversation.pk)
    else:
        form = ReportForm()

    return render(request, 'messaging/report_message.html', {'msg': msg, 'form': form})


@login_required
def reveal_email(request, conv_id):
    conv = get_object_or_404(Conversation, pk=conv_id, participants=request.user)
    other = conv.get_other_participant(request.user)

    user_sent = conv.messages.filter(sender=request.user, is_system=False).exists()
    other_sent = other and conv.messages.filter(sender=other, is_system=False).exists()

    if not (user_sent and other_sent):
        django_messages.error(
            request,
            'Vous devez avoir échangé au moins un message de chaque côté avant de partager votre email.'
        )
        return redirect('messaging:conversation', pk=conv_id)

    if conv.messages.filter(sender=request.user, is_system=True).exists():
        django_messages.info(request, 'Vous avez déjà partagé votre adresse email dans cette conversation.')
        return redirect('messaging:conversation', pk=conv_id)

    if request.method == 'POST':
        shared_info = request.POST.get('shared_info', '').strip()
        if not shared_info:
            shared_info = request.user.email
        Message.objects.create(
            conversation=conv,
            sender=request.user,
            body=shared_info,
            is_system=True,
        )
        conv.save()
        _send_reveal_notification(request, conv, shared_info, other)
        django_messages.success(request, 'Vos coordonnées ont été partagées.')
        return redirect('messaging:conversation', pk=conv_id)

    return render(request, 'messaging/reveal_email.html', {
        'conv': conv,
        'other': other,
        'default_info': request.user.email,
    })
