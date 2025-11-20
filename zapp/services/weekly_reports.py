import re
from datetime import date, timedelta
from django.utils.timezone import now
from ..models import *
from .t_model import *


DEFAULT_WEEKLY_PROMPT_INITIAL = (
"Ниже приведены несколько звонков отдела продаж. Каждый звонок пронумерован — в формате: '<ID>номер', где <ID> — это уникальный идентификатор звонка в базе данных.\n"

"Твоя задача: выявить ровно 5 наиболее часто встречающихся проблем клиентов, которые помешали совершить покупку.\n"

"Для каждой проблемы  укажи:\n"

"Название проблемы в формате: 'Ошибка N: Название проблемы;\n"
"Количество повторений — в точном формате: 'Количество повторений: N';\n"
"Несколько примеров (по одному на строку), начиная с тире и заканчивая в скобках 'звонок <ID>'.\n"
"Не добавляй рекомендации, выводы или блоки 'Итог'. Только проблемы, как описано выше.\n"

"Используй следующий формат:\n"

"Проблема 1: Название проблемы\n"
"Проблема 2: Название проблемы\n"
"Проблема 3: Название проблемы\n"
"Проблема 4: Название проблемы\n"
"Проблема 5: Название проблемы\n"

"Пример вывода:\n"

"Проблема 1: Недостаточное выявление потребностей клиента\n"

"Количество повторений: 3\n"

"Клиент не смог объяснить свои потребности, менеджер не задал уточняющих вопросов (звонок ID)\n"
"Менеджер не уточнил сроки реализации проекта (звонок ID)\n"
"Не были выявлены ключевые критерии выбора продукта (звонок ID)\n"
"Проблема 2: Отсутствие работы с возражениями\n"

"Количество повторений: 2\n"

"Клиент выразил сомнения, но менеджер не предложил аргументов (звонок ID)\n"
"Возражение по цене не было обработано (звонок ID)\n"
"Проблема 3: Недостаточная презентация продукта\n"

"Количество повторений: 1\n"

"Клиент не понял суть предложения (звонок ID)\n\n"
)


def build_prompt_with_existing_insights(insights, calls_text):
    known_errors_block = "\n".join(
        f"Причина {i+1}: {insight.title.strip()}"
        for i, insight in enumerate(insights)
    )

    return (
"Ниже приведены несколько звонков отдела продаж. Каждый звонок пронумерован — в формате: '<ID>номер', где <ID> — это уникальный идентификатор звонка в базе данных.\n"

"Твоя задача: выявить ровно 5 наиболее часто встречающихся проблем клиентов, которые помешали совершить покупку.\n"

"Для каждой проблемы  укажи:\n"

"Название проблемы в формате: 'Ошибка N: Название проблемы;\n"
"Количество повторений — в точном формате: 'Количество повторений: N';\n"
"Несколько примеров (по одному на строку), начиная с тире и заканчивая в скобках 'звонок <ID>'.\n"
"Не добавляй рекомендации, выводы или блоки 'Итог'. Только проблемы, как описано выше.\n"

"Используй следующий формат:\n"

"Проблема 1: Название проблемы\n"
"Проблема 2: Название проблемы\n"
"Проблема 3: Название проблемы\n"
"Проблема 4: Название проблемы\n"
"Проблема 5: Название проблемы\n"

"Пример вывода:\n"

"Проблема 1: Недостаточное выявление потребностей клиента\n"

"Количество повторений: 3\n"

"Клиент не смог объяснить свои потребности, менеджер не задал уточняющих вопросов (звонок ID)\n"
"Менеджер не уточнил сроки реализации проекта (звонок ID)\n"
"Не были выявлены ключевые критерии выбора продукта (звонок ID)\n"
"Проблема 2: Отсутствие работы с возражениями\n"

"Количество повторений: 2\n"

"Клиент выразил сомнения, но менеджер не предложил аргументов (звонок ID)\n"
"Возражение по цене не было обработано (звонок ID)\n"
"Проблема 3: Недостаточная презентация продукта\n"

"Количество повторений: 1\n"

"Клиент не понял суть предложения (звонок ID)\n\n"

f"{calls_text}\n"
)

def get_week_bounds(today=None):
    """
    Возвращает дату начала (понедельник) и конца (воскресенье) текущей недели.
    """
    today = today or now().date()
    start = today - timedelta(days=today.weekday())  # понедельник
    end = start + timedelta(days=6)                  # воскресенье
    return start, end


def get_or_create_active_weekly_report(organization):
    """
    Возвращает активный недельный срез. Если нет — создаёт.
    Также завершает предыдущие устаревшие срезы.
    """
    week_start, week_end = get_week_bounds()

    # Деактивируем устаревшие
    WeeklyReport.objects.filter(organization=organization, is_active=True)\
        .exclude(week_start=week_start).update(is_active=False)

    # Пытаемся найти активный
    report = WeeklyReport.objects.filter(
        organization=organization,
        week_start=week_start,
        is_active=True
    ).first()

    if report:
        return report

    # Если нет — создаём новый
    return WeeklyReport.objects.create(
        organization=organization,
        week_start=week_start,
        week_end=week_end,
        is_active=True
    )


def parse_insight_response(text: str) -> list[dict]:
    insights = []
    current = None

    lines = text.replace("=== RESPONSE ===", "").strip().splitlines()

    for line in lines:
        line = line.strip()

        # Парсим заголовок "Проблема 1: ..."
        match_title = re.match(r"(Ошибка|Проблема)\s+\d+:\s+(.+)", line)
        if match_title:
            if current:
                insights.append(current)
            current = {"title": match_title.group(2).strip(), "frequency": 0, "examples": []}
            continue

        # Парсим "Количество повторений: N"
        match_freq = re.match(r"Количество повторений:\s+(\d+)", line)
        if match_freq and current:
            current["frequency"] = int(match_freq.group(1))
            continue

        # Парсим примеры
        if line.startswith("-") and current:
            current["examples"].append(line.lstrip("-").strip())

    if current:
        insights.append(current)

    return insights

    
def extract_request_ids_from_text(text):
    """
    Ищет все ID звонков в тексте по шаблону 'звонок <число>'.
    Корректно работает даже если 'звонок' в скобках или в кавычках.
    """
    matches = re.findall(r"звонок\s*(\d+)", text.lower())
    return list(map(int, matches))


def save_weekly_insights(response_text, report):
    parsed = parse_insight_response(response_text)

    for insight_data in parsed:
        title = insight_data["title"].strip()
        frequency = insight_data.get("frequency") or 0

        # Пропускаем инсайты без повторений и примеров
        if frequency == 0 or not insight_data["examples"]:
            continue
        
        # Обновляем или создаем инсайт
        insight, created = WeeklyInsight.objects.update_or_create(
            report=report,
            title__iexact=title,
            defaults={"title": title, "frequency": frequency}
        )

        # Добавляем новые примеры
        for example_line in insight_data["examples"]:
            example = InsightExample.objects.create(insight=insight, text=example_line)
            request_ids = extract_request_ids_from_text(example_line)

            for req_id in request_ids:
                incoming = IncomingRequest.objects.filter(id=req_id).first()
                if incoming:
                    example.incoming_requests.add(incoming)


def analyze_weekly_insights(org, specific_report=None, custom_prompt=None):
    
    report = specific_report or get_or_create_active_weekly_report(org)

    requests = IncomingRequest.objects.filter(
        organization=org,
        created_at__date__range=(report.week_start, report.week_end),
        ignored=False,
    ).order_by("created_at")
    batches = [requests[i:i + 20] for i in range(0, len(requests), 20)]
    for batch in batches:
        calls_text = "\n".join(
            f"звонок {req.id}: {req.related_s2t_requests.last().transcribed_text.strip()}"
            for req in batch
            if req.related_s2t_requests.exists() and req.related_s2t_requests.last().transcribed_text
        )

        if calls_text == '':
            continue

        prompt = DEFAULT_WEEKLY_PROMPT_INITIAL + "\n\n" + calls_text
        client = init_tmodel_client(api_key=org.donkit_api_key)
        response, _, _ = send_question_to_tlite(client, prompt)
        if response:
            save_weekly_insights(response, report)


def bootstrap_weekly_reports():
    start_date = date(2025, 1, 1)
    end_date = now().date()

    orgs = Organization.objects.all()

    for org in orgs:
        date_cursor = start_date - timedelta(days=start_date.weekday())  # начнем с понедельника

        while date_cursor <= end_date:
            week_start = date_cursor
            week_end = week_start + timedelta(days=6)

            WeeklyReport.objects.get_or_create(
                organization=org,
                week_start=week_start,
                week_end=week_end,
                defaults={"is_active": False}
            )
            date_cursor += timedelta(days=7)

