# Catégories signalées par Mistral qui ne bloquent pas la publication :
# l'annonce est publiée, mais la raison reste enregistrée pour l'admin.
NON_BLOCKING_CATEGORIES = {'pii'}

CATEGORY_TRANSLATIONS = {
    'sexual': "Contenu sexuel explicite",
    'hate_and_discrimination': "Discours haineux ou discriminatoire",
    'violence_and_threats': "Violence ou menaces",
    'dangerous_and_criminal_content': "Contenu dangereux ou illégal",
    'selfharm': "Incitation à l’automutilation ou au suicide",
    'health': "Conseils médicaux non autorisés",
    'financial': "Conseils financiers non autorisés",
    'law': "Conseils juridiques non autorisés",
    'pii': "Partage ou demande d'informations personnelles",
    'api_error': "Erreur technique lors de la création de l'annonce. Cliquez sur Modifier l'annonce et republiez votre annonce sans rien changer."
}
