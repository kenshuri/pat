# Celery + Redis — Infrastructure de base — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mettre en place l'infrastructure Celery + Redis (worker + beat) avec Docker Compose en local et Railway en production, avec une tâche de démo `ping` pour vérifier que tout fonctionne.

**Architecture:** Django envoie des tâches à Redis (broker). Le Celery worker lit Redis et exécute les tâches. Celery Beat déclenche les tâches planifiées selon un schedule. En local, Docker Compose orchestre Redis + worker + beat. En production, 3 services Railway séparés pointent sur le même repo.

**Tech Stack:** Celery 5.4+, Redis 7, celery[redis], Docker Compose, uv

---

## Fichiers touchés

| Fichier | Action | Rôle |
|---|---|---|
| `pyproject.toml` | Modifier | Ajouter `celery[redis]` |
| `config/celery.py` | Créer | App Celery centrale |
| `config/__init__.py` | Modifier | Charger Celery au démarrage Django |
| `config/settings.py` | Modifier | Ajouter settings `CELERY_*` |
| `core/tasks.py` | Créer | Tâche de démo `ping` |
| `Dockerfile` | Créer | Image pour worker/beat (Docker + Railway) |
| `docker-compose.yml` | Créer | Redis + worker + beat en local |
| `.env` | Modifier | Ajouter `REDIS_URL` |

---

## Task 1 : Installer la dépendance Celery

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1 : Ajouter celery[redis] aux dépendances**

Dans `pyproject.toml`, dans le bloc `dependencies`, ajouter après la ligne `"pillow>=12.0.0",` :

```toml
"celery[redis]>=5.4",
```

- [ ] **Step 2 : Installer la dépendance**

```bash
uv sync
```

Résultat attendu : `celery` et `redis` apparaissent dans `.venv/Lib/site-packages/`.

- [ ] **Step 3 : Vérifier l'installation**

```bash
uv run celery --version
```

Résultat attendu : `5.x.x (quelque chose)`

- [ ] **Step 4 : Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add celery[redis]"
```

---

## Task 2 : Créer l'app Celery et la brancher sur Django

**Files:**
- Create: `config/celery.py`
- Modify: `config/__init__.py`

**Explication :** `config/celery.py` crée l'instance Celery centrale. `config/__init__.py` l'importe pour que Django la charge dès le démarrage — sans ça, Celery ne découvrirait pas les tâches définies dans les apps.

- [ ] **Step 1 : Créer `config/celery.py`**

```python
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('config')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
```

> **Explication ligne par ligne :**
> - `os.environ.setdefault` : garantit que Django est configuré avant Celery, même si on lance celery directement en CLI
> - `Celery('config')` : nomme l'app "config" (nom arbitraire, utilisé dans les logs)
> - `config_from_object(..., namespace='CELERY')` : dit à Celery de lire tous les settings Django préfixés par `CELERY_` (ex: `CELERY_BROKER_URL`)
> - `autodiscover_tasks()` : scanne chaque app Django listée dans `INSTALLED_APPS` et importe automatiquement son fichier `tasks.py`

- [ ] **Step 2 : Modifier `config/__init__.py`**

Remplacer le contenu actuel (vide) par :

```python
from .celery import app as celery_app

__all__ = ('celery_app',)
```

- [ ] **Step 3 : Vérifier que Django démarre toujours**

```bash
uv run python manage.py check
```

Résultat attendu : `System check identified no issues (0 silenced).`

- [ ] **Step 4 : Commit**

```bash
git add config/celery.py config/__init__.py
git commit -m "feat: add celery app configuration"
```

---

## Task 3 : Ajouter les settings Celery dans Django

**Files:**
- Modify: `config/settings.py`

**Explication :** Les settings préfixés `CELERY_` sont lus automatiquement par Celery grâce au `namespace='CELERY'` défini dans `config/celery.py`.

- [ ] **Step 1 : Ajouter le bloc Celery à la fin de `config/settings.py`**

Ajouter après la dernière ligne (ligne 199, après `DEFAULT_FROM_EMAIL = ...`) :

```python
# Celery
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Europe/Paris'
CELERY_BEAT_SCHEDULE = {}
```

> **Explication :**
> - `BROKER_URL` : où Celery envoie les tâches (Redis)
> - `RESULT_BACKEND` : où Celery stocke les résultats des tâches (aussi Redis, TTL 24h par défaut)
> - `ACCEPT_CONTENT` + `TASK_SERIALIZER` : format JSON pour les messages (plus sûr que pickle)
> - `BEAT_SCHEDULE` : vide pour l'instant — sera rempli feature par feature (ex: newsletter lundi matin)

- [ ] **Step 2 : Ajouter `REDIS_URL` dans `.env`**

Ajouter à la fin du fichier `.env` :

```
REDIS_URL=redis://localhost:6379/0
```

- [ ] **Step 3 : Vérifier**

```bash
uv run python manage.py check
```

Résultat attendu : `System check identified no issues (0 silenced).`

- [ ] **Step 4 : Commit**

```bash
git add config/settings.py .env
git commit -m "feat: add celery settings"
```

---

## Task 4 : Créer la tâche de démo `ping`

**Files:**
- Create: `core/tasks.py`

**Explication :** `@shared_task` (plutôt que `@app.task`) permet de définir des tâches sans importer directement l'instance `app` de `config/celery.py`. C'est la bonne pratique pour les apps Django réutilisables.

- [ ] **Step 1 : Créer `core/tasks.py`**

```python
from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task
def ping():
    logger.info("Celery ping task executed.")
    return "pong"
```

- [ ] **Step 2 : Vérifier que Django importe la tâche sans erreur**

```bash
uv run python manage.py shell -c "from core.tasks import ping; print(ping)"
```

Résultat attendu : `<@task: core.tasks.ping of config at 0x...>`

- [ ] **Step 3 : Commit**

```bash
git add core/tasks.py
git commit -m "feat: add ping demo task"
```

---

## Task 5 : Créer le Dockerfile

**Files:**
- Create: `Dockerfile`

**Explication :** Le Dockerfile est nécessaire pour deux choses : (1) Docker Compose en local (worker + beat tournent dans des containers), (2) Railway pour les services worker et beat en production. Le service Django existant sur Railway utilise peut-être déjà un Dockerfile ou le buildpack Railway — vérifier si un Dockerfile existe déjà avant de créer.

- [ ] **Step 1 : Créer `Dockerfile` à la racine**

```dockerfile
FROM python:3.13-slim

WORKDIR /app

# Copie uv depuis son image officielle
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Installe les dépendances en premier (layer cache Docker)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copie le code source
COPY . .
```

> **Explication :**
> - `python:3.13-slim` : image légère, correspond à `requires-python = ">=3.13"` dans `pyproject.toml`
> - Copier `pyproject.toml` + `uv.lock` AVANT le code source : si le code change mais pas les deps, Docker réutilise le layer `uv sync` depuis le cache
> - `--no-dev` : n'installe pas les dépendances dev (openpyxl, requests) dans les containers de prod

- [ ] **Step 2 : Vérifier que le build Docker fonctionne**

```bash
docker build -t pat-test .
```

Résultat attendu : `Successfully built ...` sans erreur.

- [ ] **Step 3 : Commit**

```bash
git add Dockerfile
git commit -m "feat: add Dockerfile for worker/beat"
```

---

## Task 6 : Créer docker-compose.yml

**Files:**
- Create: `docker-compose.yml`

**Explication :** Docker Compose orchestre Redis + worker + beat ensemble. Django tourne toujours séparément avec `uv run python manage.py runserver` (plus rapide pour le dev, hot-reload natif). Le `volume: .:/app` permet au worker de voir les changements de code sans rebuild.

- [ ] **Step 1 : Créer `docker-compose.yml` à la racine**

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

> **Explication :**
> - `redis://redis:6379/0` dans les containers : `redis` est le nom DNS du service Redis dans le réseau Docker Compose (pas `localhost`)
> - `env_file: .env` : les containers lisent ton `.env` local (DATABASE_URL, API keys, etc.)
> - `environment: REDIS_URL=...` : surcharge la valeur de `.env` pour que worker/beat pointent vers le Redis Docker et non `localhost`
> - `depends_on: redis` : Docker démarre Redis avant le worker/beat (mais n'attend pas que Redis soit prêt — suffisant pour notre cas)

- [ ] **Step 2 : Démarrer les services**

```bash
docker compose up
```

Résultat attendu dans les logs :
```
redis     | Ready to accept connections
worker    | celery@... ready.
beat      | beat: Starting...
```

- [ ] **Step 3 : Dans un second terminal, lancer Django**

```bash
uv run python manage.py runserver
```

- [ ] **Step 4 : Tester la tâche ping**

Dans un troisième terminal :

```bash
uv run python manage.py shell
```

```python
from core.tasks import ping
result = ping.delay()
print(result.get(timeout=10))
```

Résultat attendu : `'pong'`

Dans les logs du worker (terminal docker compose) :
```
Task core.tasks.ping[...] succeeded in 0.001s: 'pong'
```

- [ ] **Step 5 : Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add docker-compose for local redis + celery"
```

---

## Task 7 : Configurer Railway (production)

Cette tâche est manuelle dans le dashboard Railway.

- [ ] **Step 1 : Ajouter un service Redis**

Dans ton projet Railway :
1. Cliquer "New Service" → "Database" → "Redis"
2. Railway crée automatiquement la variable `REDIS_URL` sur ce service

- [ ] **Step 2 : Partager REDIS_URL avec Django**

Dans le service Django existant sur Railway :
1. Aller dans "Variables"
2. Ajouter : `REDIS_URL` = `${{Redis.REDIS_URL}}` (Railway résout cette référence automatiquement)

- [ ] **Step 3 : Créer le service Celery worker**

1. Cliquer "New Service" → "GitHub Repo" → sélectionner le même repo
2. Dans "Settings" → "Deploy" → "Start Command" :
   ```
   celery -A config worker --loglevel=info
   ```
3. Dans "Variables", ajouter toutes les variables d'env nécessaires (copier depuis le service Django) + `REDIS_URL=${{Redis.REDIS_URL}}`

- [ ] **Step 4 : Créer le service Celery beat**

1. Répéter l'étape 3 avec la commande :
   ```
   celery -A config beat --loglevel=info
   ```

- [ ] **Step 5 : Vérifier les logs Railway**

Dans les logs du service worker, chercher :
```
celery@... ready.
```

Dans les logs du service beat :
```
beat: Starting...
```

---

## Résumé des commandes utiles

```bash
# Local — démarrer l'infra
docker compose up

# Local — arrêter l'infra
docker compose down

# Local — voir les logs du worker seulement
docker compose logs -f worker

# Local — tester une tâche
uv run python manage.py shell -c "from core.tasks import ping; print(ping.delay().get(timeout=5))"

# Vérifier que Celery voit bien les tâches
uv run celery -A config inspect registered
```
