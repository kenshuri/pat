def unread_messages_count(request):
    if not request.user.is_authenticated:
        return {'unread_messages_count': 0, 'pending_plays_count': 0}
    from messaging.models import Message
    from shows.models import PlayMembership
    from django.db.models import Q
    msg_count = (
        Message.objects
        .filter(conversation__participants=request.user, read_at__isnull=True)
        .exclude(sender=request.user)
        .values('conversation')
        .distinct()
        .count()
    )
    plays_count = PlayMembership.objects.filter(
        Q(play__user=request.user, direction=PlayMembership.DIRECTION_REQUEST, status=PlayMembership.STATUS_PENDING) |
        Q(direction=PlayMembership.DIRECTION_INVITE, status=PlayMembership.STATUS_PENDING, user=request.user)
    ).count()
    return {'unread_messages_count': msg_count, 'pending_plays_count': plays_count}
