import time
from datetime import date, timedelta
from django.utils.timezone import now
from ..models import *
from .weekly_reports import *
from .weekly_errors import *
from .weekly_factors import *


def get_week_ranges(start_date: date, end_date: date):
    """
    Генерирует список кортежей (week_start, week_end) от start_date до end_date включительно.
    """
    current = start_date - timedelta(days=start_date.weekday())  # понедельник текущей недели
    result = []

    while current <= end_date:
        week_start = current
        week_end = week_start + timedelta(days=6)
        result.append((week_start, week_end))
        current += timedelta(weeks=1)

    return result


def backfill_WeeklyReports(start_date=date(2025, 5, 1), end_date=date(2025, 6, 14)):
    """
    Создаёт WeeklyReport и запускает анализ для каждой организации и недели между start_date и end_date.
    """
    weeks = get_week_ranges(start_date, end_date)
    organizations = Organization.objects.all()
    created = 0

    for org in organizations:
        for week_start, week_end in weeks:
            report, created_obj = WeeklyReport.objects.get_or_create(
                organization=org,
                week_start=week_start,
                week_end=week_end,
                defaults={"is_active": False}
            )
            if created_obj:
                created += 1

            # Анализируем по этой неделе
            analyze_weekly_insights(org, specific_report=report)



def backfill_ErrorReports(org, start_date, end_date):
    """
    Создаёт WeeklyErrorReport для указанной организации и анализирует с заданным промптом.
    """
    weeks = get_week_ranges(start_date, end_date)

    for week_start, week_end in weeks:
        report, _ = WeeklyErrorReport.objects.get_or_create(
            organization=org,
            week_start=week_start,
            week_end=week_end,
            defaults={"is_active": False}
        )
        analyze_weekly_errors(org, specific_report=report)
        time.sleep(30)


def backfill_FactorReports(org, start_date, end_date):
    """
    Создаёт WeeklyFactorReport для указанной организации и анализирует с заданным промптом.
    """
    weeks = get_week_ranges(start_date, end_date)

    for week_start, week_end in weeks:
        report, _ = WeeklyFactorReport.objects.get_or_create(
            organization=org,
            week_start=week_start,
            week_end=week_end,
            defaults={"is_active": False}
        )
        analyze_weekly_factors(org, specific_report=report)
        time.sleep(30)