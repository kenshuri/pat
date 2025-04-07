from django.core.management.base import BaseCommand
from core.models import Offer
from openpyxl import Workbook


class Command(BaseCommand):
    help = 'Exporte les offres vers un fichier Excel avec ID, contenu modération et une colonne "Section" vide.'

    def handle(self, *args, **options):
        filename = 'offers_to_categorize.xlsx'

        # Création du fichier Excel
        wb = Workbook()
        ws = wb.active
        ws.title = "Offres"

        # Écriture de l'en-tête
        ws.append(['ID', 'Offer', 'Section'])

        # Écriture des lignes avec données
        for offer in Offer.objects.all().order_by('id'):
            ws.append([
                offer.id,
                offer.get_moderation_text(),
                ''  # Colonne "Section" vide
            ])

        # Sauvegarde
        wb.save(filename)
        self.stdout.write(self.style.SUCCESS(f"{Offer.objects.count()} offres exportées dans {filename}"))
