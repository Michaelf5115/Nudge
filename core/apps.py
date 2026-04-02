import os
import sys

from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        # Start the digest cron scheduler in the main process only.
        # Django's dev server spawns a reloader child; RUN_MAIN='true' marks the child.
        # In production (gunicorn) there is no reloader, so we always start.
        is_dev_reloader_parent = 'runserver' in sys.argv and os.environ.get('RUN_MAIN') != 'true'
        if not is_dev_reloader_parent:
            from .services.digest import start_digest_cron
            start_digest_cron()
