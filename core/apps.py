import os
import sys

from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        # Only start APScheduler when actually serving requests, not during
        # management commands (check, migrate, shell, etc.).
        is_runserver = 'runserver' in sys.argv and os.environ.get('RUN_MAIN') == 'true'
        is_gunicorn = 'gunicorn' in sys.argv[0]
        if is_runserver or is_gunicorn:
            from .services.digest import start_digest_cron
            start_digest_cron()
