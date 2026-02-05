from django.apps import AppConfig
from django.db.backends.signals import connection_created

from .db_pragmas import enable_sqlite_pragmas


class CoreConfig(AppConfig):
    name = "core"

    def ready(self):
        connection_created.connect(enable_sqlite_pragmas)
