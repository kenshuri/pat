#!/bin/sh
set -e
python manage.py collectstatic --noinput
python manage.py migrate
exec gunicorn config.wsgi --bind 0.0.0.0:8080 --workers 2
