"""Filtrage des settings sensibles dans les rapports d'erreur Django.

Le filtre par défaut masque les settings dont le nom contient API, TOKEN, KEY,
SECRET, PASS ou SIGNATURE. Les URLs de connexion Redis et Celery n'entrent dans
aucune de ces catégories : leur mot de passe partait donc en clair dans chaque
email d'erreur envoyé aux ADMINS.
"""
import re

from django.views.debug import SafeExceptionReporterFilter


class RedactedSettingsReporterFilter(SafeExceptionReporterFilter):
    hidden_settings = re.compile(
        "API|TOKEN|KEY|SECRET|PASS|SIGNATURE|HTTP_COOKIE"
        "|REDIS|BROKER|RESULT_BACKEND|DATABASE_URL",
        flags=re.I,
    )
