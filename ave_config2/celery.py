from __future__ import absolute_import, unicode_literals
import os
from celery.schedules import crontab
from celery import Celery
from django.conf import settings

# Указываем Django настройки для Celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ave_config2.settings')

app = Celery('ave_config2')

# Загружаем настройки Celery из Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Автоматическое обнаружение задач
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')

app.conf.beat_schedule = {
    'check_transcription_status_every_2_minutes': {
        'task': 'zapp.tasks.schedule_transcription_checks',  # Полный путь к задаче
        'schedule': 60.0,  # Интервал в секундах (1 минуту)
    },
    "update_deal_statuses_daily": {
        "task": "zapp.tasks.update_deal_statuses",
        "schedule": crontab(minute=1, hour=0),  # Запуск в 00:01 каждый день
    },
    "generate_weekly_insights_daily": {
        "task": "zapp.tasks.generate_weekly_insights_for_all",
        "schedule": crontab(minute=30, hour=1),  # каждый день в 01:30
    },
    "generate_weekly_reports_every_monday": {
        "task": "zapp.tasks.generate_weekly_reports_for_all",
        "schedule": crontab(minute=0, hour=2, day_of_week=1),  # по понедельникам в 02:00
    },
}

app.conf.timezone = "Europe/Moscow"  # Укажите свой часовой пояс