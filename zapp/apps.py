# zapp/apps.py
from django.apps import AppConfig


class ZappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'zapp'

    def ready(self):
        import zapp.signals  # 👈 подключаем сигналы