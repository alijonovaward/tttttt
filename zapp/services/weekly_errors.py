# services/weekly_errors.py

import re
from datetime import timedelta
from django.utils.timezone import now
from ..models import *
from .t_model import *

DEFAULT_WEEKLY_ERROR_PROMPT_INITIAL = (
"""
Ниже приведены несколько звонков отдела продаж. Каждый звонок пронумерован — в формате: '<ID>номер', где <ID> — это уникальный идентификатор звонка в базе данных.

Твоя задача: выявить ровно 5 наиболее часто встречающихся ошибок или проблем в этих звонках. Один звонок – одна ошибка.

Для каждой ошибки укажи:

Название ошибки в формате: 'Ошибка N: Название ошибки';
Количество звонков с такими ошиками — в точном формате: 'Количество повторений: N';
Несколько примеров (по одному на строку), начиная с тире и заканчивая в скобках 'звонок <ID>'.
Не добавляй рекомендации, выводы или блоки 'Итог'. Только ошибки, как описано выше.

Используй следующий формат:

Ошибка 1: название ошибки
Ошибка 2: Название ошибки
Ошибка 3: Название ошибки
Ошибка 4: Название ошибки
Ошибка 5: Название ошибки 

Пример вывода:

Ошибка 1: Недостаточное выявление потребностей клиента

Количество повторений: 3

Клиент не смог объяснить свои потребности, менеджер не задал уточняющих вопросов (звонок 12)
Менеджер не уточнил сроки реализации проекта (звонок 15)
Не были выявлены ключевые критерии выбора продукта (звонок 18)
Ошибка 2: Отсутствие работы с возражениями

Количество повторений: 2

Клиент выразил сомнения, но менеджер не предложил аргументов (звонок 10)
Возражение по цене не было обработано (звонок 14)
Ошибка 3: Недостаточная презентация продукта

Количество повторений: 1

Менеджер не рассказал о ключевых преимуществах продукта (звонок 13)
"""
)


def build_prompt_with_existing_errors(errors, calls_text):
    known_errors_block = "\n".join(
        f"Ошибка {i+1}: {error.title.strip()}"
        for i, error in enumerate(errors)
    )

    return (
f"""
Ниже приведены несколько звонков отдела продаж. Каждый звонок пронумерован — в формате: '<ID>номер', где <ID> — это уникальный идентификатор звонка в базе данных.

Твоя задача: выявить ровно 5 наиболее часто встречающихся ошибок или проблем в этих звонках. Один звонок – одна ошибка.

Для каждой ошибки укажи:

Название ошибки в формате: 'Ошибка N: Название ошибки';
Количество звонков с такими ошибками — в точном формате: 'Количество повторений: N';
Несколько примеров (по одному на строку), начиная с тире и заканчивая в скобках 'звонок <ID>'.
Не добавляй рекомендации, выводы или блоки 'Итог'. Только ошибки, как описано выше.

Вот текущий список ошибок. Используй только эти названия ошибок (если они подходят под контекст):

{known_errors_block}

Если в звонках чаще встречается другая ошибка, добавь её в список с новым номером (например, Ошибка 6: Новое название ошибки) и используй её в дальнейшем.

Пример вывода:

Ошибка 1: Недостаточное выявление потребностей клиента

Количество повторений: 3

Клиент не смог объяснить свои потребности, менеджер не задал уточняющих вопросов (звонок 12)
Менеджер не уточнил сроки реализации проекта (звонок 15)
Не были выявлены ключевые критерии выбора продукта (звонок 18)
Ошибка 2: Отсутствие работы с возражениями

Количество повторений: 2

Клиент выразил сомнения, но менеджер не предложил аргументов (звонок 10)
Возражение по цене не было обработано (звонок 14)
Ошибка 3: Недостаточная презентация продукта

Количество повторений: 1

Менеджер не рассказал о ключевых преимуществах продукта (звонок 13)

{calls_text}
"""
)


def get_week_bounds(today=None):
    """
    Возвращает дату начала (понедельник) и конца (воскресенье) текущей недели.
    """
    today = today or now().date()
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    return start, end


def get_or_create_active_weekly_error_report(organization):
    """
    Возвращает активный недельный отчет по ошибкам. Если нет — создаёт.
    Также завершает предыдущие устаревшие отчеты.
    """
    week_start, week_end = get_week_bounds()

    # Деактивируем устаревшие
    WeeklyErrorReport.objects.filter(organization=organization, is_active=True)\
        .exclude(week_start=week_start).update(is_active=False)

    # Пытаемся найти активный
    report = WeeklyErrorReport.objects.filter(
        organization=organization,
        week_start=week_start,
        is_active=True
    ).first()

    if report:
        return report

    # Если нет — создаём новый
    return WeeklyErrorReport.objects.create(
        organization=organization,
        week_start=week_start,
        week_end=week_end,
        is_active=True
    )


def parse_error_response(text: str) -> list[dict]:
    errors = []
    current = None

    lines = text.replace("=== RESPONSE ===", "").strip().splitlines()

    for line in lines:
        line = line.strip()

        # Парсим заголовок "Ошибка 1: ..."
        match_title = re.match(r"(Ошибка)\s+\d+:\s+(.+)", line)
        if match_title:
            if current:
                errors.append(current)
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
        errors.append(current)

    return errors


def extract_request_ids_from_text(text):
    """
    Ищет все ID звонков в тексте по шаблону 'звонок <число>'.
    """
    matches = re.findall(r"звонок\s*(\d+)", text.lower())
    return list(map(int, matches))


def save_weekly_errors(response_text, report):
    parsed = parse_error_response(response_text)

    for error_data in parsed:
        title = error_data["title"].strip()
        frequency = error_data.get("frequency") or 0

        if frequency == 0 or not error_data["examples"]:
            continue
        
        error, created = WeeklyError.objects.update_or_create(
            report=report,
            title__iexact=title,
            defaults={"title": title, "frequency": frequency}
        )

        for example_line in error_data["examples"]:
            example = ErrorExample.objects.create(error=error, text=example_line)
            request_ids = extract_request_ids_from_text(example_line)

            for req_id in request_ids:
                incoming = IncomingRequest.objects.filter(id=req_id).first()
                if incoming:
                    example.incoming_requests.add(incoming)


def analyze_weekly_errors(org, specific_report=None):
    """
    Анализирует ошибки за неделю для организации.
    """
    report = specific_report or get_or_create_active_weekly_error_report(org)

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

        existing_errors = report.errors.all()

        if existing_errors.exists():
            prompt = build_prompt_with_existing_errors(existing_errors, calls_text)
        else:
            prompt = DEFAULT_WEEKLY_ERROR_PROMPT_INITIAL + "\n\n" + calls_text

        client = init_tmodel_client(api_key=org.donkit_api_key)
        response, _, _ = send_question_to_tlite(client, prompt)
        if response:
            save_weekly_errors(response, report)

