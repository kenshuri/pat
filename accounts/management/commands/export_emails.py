import csv
from django.core.management.base import BaseCommand
from accounts.models import CustomUser  # Remplace `yourapp` par le nom de ton app

class Command(BaseCommand):
    help = 'Export user emails to a CSV file for Mailjet'

    def handle(self, *args, **options):
        with open('emails.csv', 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            for user in CustomUser.objects.all():
                writer.writerow([user.email])
        self.stdout.write(self.style.SUCCESS('Fichier emails.csv généré avec succès.'))
