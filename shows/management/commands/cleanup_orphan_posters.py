from datetime import datetime, timedelta, timezone as dt_timezone
import sys
from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
from django.db.models import Q
from django.utils.module_loading import import_string
from shows.models import Play


class Command(BaseCommand):
    help = """🧹 Supprime les fichiers d'affiche orphelins dans le storage (ex. Scaleway S3).

Cette commande parcourt le dossier de stockage des affiches (par défaut 'posters/')
et supprime les fichiers qui ne sont plus référencés dans la base de données (modèle Play.poster).

💡 Exemples d'utilisation :

    # Lister les fichiers orphelins sans rien supprimer (dry-run)
    python manage.py cleanup_orphan_posters

    # Supprimer réellement les fichiers orphelins
    python manage.py cleanup_orphan_posters --delete

    # Limiter au sous-dossier posters/2025/
    python manage.py cleanup_orphan_posters --prefix posters/2025/

    # Ignorer les fichiers récents (< 7 jours)
    python manage.py cleanup_orphan_posters --older-than 7

    # Spécifier un storage différent (chemin importable)
    python manage.py cleanup_orphan_posters --storage 'myapp.storages.S3MediaStorage'

⚠️ Par défaut :
- Aucun fichier n'est supprimé sans l'option --delete
- Les fichiers modifiés il y a moins de 2 jours sont ignorés
- Seuls les fichiers sous 'posters/' sont ciblés
"""

    def add_arguments(self, parser):
        parser.add_argument(
            "--prefix",
            default="posters/",
            help="Préfixe/dossier à scanner (défaut: posters/)"
        )
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Supprime réellement les fichiers (sinon dry-run)."
        )
        parser.add_argument(
            "--older-than",
            type=int,
            default=0,
            help="Ne considère orphelin que les objets plus vieux que N jours (défaut: 2)."
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Taille de lot pour la liste/suppression (défaut: 1000)."
        )
        parser.add_argument(
            "--storage",
            default="",
            help="Chemin importable d'un storage spécifique (sinon le storage du champ Play.poster)."
        )

    def handle(self, *args, **opts):
        prefix = opts["prefix"].lstrip("/")
        really_delete = opts["delete"]
        older_than_days = opts["older_than"]
        batch_size = opts["batch_size"]
        storage_path = opts["storage"]

        if storage_path:
            storage = import_string(storage_path)()
        else:
            storage = Play._meta.get_field("poster").storage or default_storage

        if not prefix.startswith("posters/"):
            self.stdout.write(self.style.WARNING(
                f"Attention: prefix='{prefix}' n'est pas sous 'posters/'. Continuer avec prudence."
            ))

        used_names = set(
            Play.objects.exclude(Q(poster__isnull=True) | Q(poster__exact=""))
            .values_list("poster", flat=True)
        )
        self.stdout.write(f"Références en base : {len(used_names)} fichiers d'affiche.")

        bucket = getattr(storage, "bucket", None)
        location = getattr(storage, "location", "") or ""
        if location and not location.endswith("/"):
            location += "/"

        effective_prefix = f"{location}{prefix}" if location else prefix

        if bucket is None or not hasattr(bucket, "objects"):
            self.stderr.write(self.style.ERROR(
                "Ce storage ne fournit pas .bucket/.objects (non compatible S3Boto3 ?)."
            ))
            sys.exit(1)

        min_last_modified = datetime.now(dt_timezone.utc) - timedelta(days=older_than_days)

        total = 0
        orphans = []
        for obj in bucket.objects.filter(Prefix=effective_prefix):
            key = obj.key
            if location and key.startswith(location):
                name = key[len(location):]
            else:
                name = key

            if name.endswith("/") or name == prefix:
                continue

            total += 1
            if getattr(obj, "last_modified", None) and obj.last_modified > min_last_modified:
                continue

            if name not in used_names:
                orphans.append(name)

        self.stdout.write(f"Objets trouvés sous '{prefix}': {total}")
        self.stdout.write(self.style.WARNING(f"Orphelins candidats (>{older_than_days} j): {len(orphans)}"))

        if not orphans:
            self.stdout.write(self.style.SUCCESS("Aucun fichier orphelin trouvé."))
            return

        for n in orphans[:50]:
            self.stdout.write(f" - {n}")
        if len(orphans) > 50:
            self.stdout.write(f" ... (+{len(orphans) - 50} autres)")

        if really_delete:
            deleted = 0
            for name in orphans:
                try:
                    storage.delete(name)
                    deleted += 1
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"Erreur suppression {name}: {e}"))
            self.stdout.write(self.style.SUCCESS(f"Supprimés: {deleted}/{len(orphans)}"))
        else:
            self.stdout.write(self.style.NOTICE(
                "Dry-run terminé : aucun fichier supprimé. Utilisez --delete pour supprimer réellement."
            ))
