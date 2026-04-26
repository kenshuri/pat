# Celery + Redis — Infrastructure de base

**Date :** 2026-04-26
**Scope :** Mise en place de l'infra Celery/Redis uniquement. Pas de tâches métier dans cette itération.

---

## Contexte

petites-annonces-theatre.fr est un projet Django 5.1 déployé sur Railway. Les tâches asynchrones futures (modération NudeNet, alertes mail, newsletters) nécessitent une infrastructure de workers. Celery + Redis a été choisi pour sa maturité et sa valeur d'apprentissage.

---

## Architecture locale

Docker Compose orchestre trois services annexes. Django tourne séparément via `uv run python manage.py runserver`.

```
docker-compose.yml
├── redis          — broker (port 6379)
├── celery-worker  — exécute les tâches
└── celery-beat    — déclenche les tâches planifiées
```

**Commandes dev :**
```bash
docker compose up          # démarre Redis + worker + beat
uv run python manage.py runserver  # dans un terminal séparé
```

---

## Architecture Railway (production)

4 services dans le même projet Railway, tous pointant sur le même repo GitHub :

| Service | Start command |
|---|---|
| Django (existant) | `gunicorn config.wsgi` |
| Redis | Service managé Railway (pas de start command) |
| Celery worker | `celery -A config worker --loglevel=info` |
| Celery beat | `celery -A config beat --loglevel=info` |

La variable d'env `REDIS_URL` est partagée entre les 3 services applicatifs via Railway.

---

## Fichiers créés/modifiés

### `config/celery.py` (nouveau)
Configuration centrale Celery. Pointe sur `config` comme nom d'app (cohérent avec le module Django settings `config.settings`).

```python
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
app = Celery('config')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
```

### `config/__init__.py` (modifié)
Importe l'app Celery pour qu'elle soit chargée au démarrage de Django.

```python
from .celery import app as celery_app
__all__ = ('celery_app',)
```

### `config/settings.py` (modifié)
Ajout des settings Celery dans le bloc de configuration existant :

```python
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Europe/Paris'
CELERY_BEAT_SCHEDULE = {}  # vide pour l'instant, sera rempli feature par feature
```

### `docker-compose.yml` (nouveau, racine du projet)

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  worker:
    build: .
    command: uv run celery -A config worker --loglevel=info
    volumes:
      - .:/app
    env_file: .env
    environment:
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis

  beat:
    build: .
    command: uv run celery -A config beat --loglevel=info
    volumes:
      - .:/app
    env_file: .env
    environment:
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
```

### `Dockerfile` (nouveau, racine du projet)
Nécessaire pour docker-compose et pour Railway (worker + beat) :

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen
COPY . .
```

### `pyproject.toml` (modifié)
Ajout de la dépendance :
```
celery[redis]>=5.4
```

### `core/tasks.py` (nouveau)
Tâche de démo pour vérifier que l'infra fonctionne :

```python
from celery import shared_task
import logging

logger = logging.getLogger(__name__)

@shared_task
def ping():
    logger.info("Celery fonctionne.")
    return "pong"
```

---

## Vérification locale

Séquence de test après installation :

```bash
# Terminal 1
docker compose up

# Terminal 2
uv run python manage.py runserver

# Terminal 3 — déclencher la tâche de démo
uv run python manage.py shell
>>> from core.tasks import ping
>>> result = ping.delay()
>>> result.get(timeout=5)
'pong'
```

Le log du worker doit afficher `Task core.tasks.ping succeeded`.

---

## Variables d'environnement

| Variable | Local | Railway |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` (dans `.env`) | Injectée automatiquement par Railway Redis |

---

## Ce qui n'est PAS dans ce scope

- Tâches métier (modération NudeNet, alertes mail, newsletters)
- Monitoring Celery (Flower) — peut être ajouté plus tard
- Persistance des résultats de tâches (résultats stockés dans Redis, TTL par défaut 24h)
