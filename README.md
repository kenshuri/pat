# pat
Site web pour déposer des petites annonces en lien avec le théâtre

## Dev local

**Terminal 1 — Infra (Redis + Celery worker + beat) :**
```bash
docker compose up
```
> Premier lancement : ajouter `--build` pour construire les images.
> À refaire si tu modifies `pyproject.toml` ou le `Dockerfile`.

**Terminal 2 — Django :**
```bash
uv run python manage.py runserver
```

**Tester que Celery fonctionne :**
```bash
uv run python manage.py shell -c "from core.tasks import ping; print(ping.delay().get(timeout=10))"
```
Résultat attendu : `pong` + log `Task core.tasks.ping succeeded` dans le terminal Docker.
