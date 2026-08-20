"""Point d'entrée unique pour les décisions de modération prises dans l'admin.

Couvre les deux chemins possibles : les actions en masse et l'édition manuelle du
statut (formulaire de modification ou colonne `list_editable`).
"""


class ModerationDecisionMixin:
    def notify_moderation_decision(self, obj, previous_status):
        """À implémenter : appelle le notifieur adapté au modèle."""
        raise NotImplementedError

    def save_model(self, request, obj, form, change):
        previous_status = None
        if change and obj.pk:
            previous_status = (
                type(obj).objects
                .filter(pk=obj.pk)
                .values_list('moderation_status', flat=True)
                .first()
            )
        super().save_model(request, obj, form, change)
        self.notify_moderation_decision(obj, previous_status)

    def apply_moderation_decision(self, queryset, new_status):
        """Applique le statut objet par objet et notifie les auteurs concernés.

        Retourne le nombre d'objets réellement modifiés.
        """
        updated = 0
        for obj in queryset:
            previous_status = obj.moderation_status
            if previous_status == new_status:
                continue
            obj.moderation_status = new_status
            obj.save(update_fields=['moderation_status'])
            self.notify_moderation_decision(obj, previous_status)
            updated += 1
        return updated
