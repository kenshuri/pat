import csv
from django.core.management.base import BaseCommand
from core.models import Offer
from accounts.models import CustomUser

class Command(BaseCommand):
    help = 'Exporte les emails des utilisateurs ayant publié au moins une annonce'

    def handle(self, *args, **options):
        # Récupère les utilisateurs distincts ayant posté au moins une offre (non-null)
        users_with_offers = CustomUser.objects.filter(offer__isnull=False).distinct()

        with open('emails_offreurs.csv', 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            for user in users_with_offers:
                if user.email:  # Par précaution
                    writer.writerow([user.email])

        self.stdout.write(self.style.SUCCESS(f'{users_with_offers.count()} emails exportés dans emails_offreurs.csv.'))
