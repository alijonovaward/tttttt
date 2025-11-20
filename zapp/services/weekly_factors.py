# services/weekly_factors.py

import re
from datetime import timedelta
from django.utils.timezone import now
from ..models import *
from .t_model import *

DEFAULT_WEEKLY_FACTOR_PROMPT_INITIAL = (
"""
Ниже приведены несколько звонков отдела продаж. Каждый звонок пронумерован — в формате: '<ID>номер', где <ID> — это уникальный идентификатор звонка в базе данных.

Твоя задача: выявить ровно 5 наиболее часто встречающихся ошибок или проблем в этих звонках. Один звонок – одна ошибка.

Для каждой ошибки укажи:

Название ошибки в формате: 'Ошибка N: Название ошибки';
Количество звонков с такими ошиками — в точном формате: 'Количество повторений: N';
Несколько примероНиже приведены несколько звонков отдела продаж. Каждый звонок пронумерован — в формате: '<ID>номер', где <ID> — это уникальный идентификатор звонка в базе данных.

Твоя задача: выявить ровно 5 ключевых факторов принятия положительного решения клиентов о заключении сделки. Один звонок – один фактор.

Для каждого фактора укажи:

Название фактора в формате: Фактор N: Название Фактора;
Количество звонков с такими факторами — в точном формате: 'Количество повторений: N';
Несколько примеров (по одному на строку), начиная с тире и заканчивая в скобках 'звонок <ID>'.
Не добавляй рекомендации, выводы или блоки 'Итог'. Только Факторы, как описано выше.

Используй следующий формат:

Фактор 1: название Фактора
Фактор 2: Название Фактора
Фактор 3: Название Фактора
Фактор 4: Название Фактора
Фактор 5: Название Фактора

Пример вывода:

Фактор 1: понравился сайт

Количество повторений: 3

Фактор 2: выгодные условия покупки

Количество повторений: 2

Фактор 3: качественная презентация

Количество повторений: 1
"""
)


def build_prompt_with_existing_factors(factors, calls_text):
    known_factors_block = "\n".join(
        f"Фактор {i+1}: {factor.title.strip()}"
        for i, factor in enumerate(factors)
    )

    return (
f"""
Ниже приведены несколько звонков отдела продаж. Каждый звонок пронумерован — в формате: '<ID>номер', где <ID> — это уникальный идентификатор звонка в базе данных.

Твоя задача: выявить ровно 5 ключевых факторов принятия положительного решения клиентов о заключении сделки. Один звонок – один фактор.

Для каждого фактора укажи:

Название фактора в формате: Фактор N: Название Фактора;
Количество звонков с такими факторами — в точном формате: 'Количество повторений: N';
Несколько примеров (по одному на строку), начиная с тире и заканчивая в скобках 'звонок <ID>'.
Не добавляй рекомендации, выводы или блоки 'Итог'. Только Факторы, как описано выше.

Вот текущий список факторов. Используй только эти названия факторов (если они подходят под контекст):

{known_factors_block}

Если в звонках чаще встречается другие факторы, добавь их в список с новым номером (например, Фактор 6: Новое название фактора) и используй её в дальнейшем.

Пример вывода:

Фактор 1: понравился сайт

Количество повторений: 3

Фактор 2: выгодные условия покупки

Количество повторений: 2

Фактор 3: качественная презентация

Количество повторений: 1

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


def get_or_create_active_weekly_factor_report(organization):
    """
    Возвращает активный недельный отчет по факторам. Если нет — создаёт.
    Также завершает предыдущие устаревшие отчеты.
    """
    week_start, week_end = get_week_bounds()

    # Деактивируем устаревшие
    WeeklyFactorReport.objects.filter(organization=organization, is_active=True)\
        .exclude(week_start=week_start).update(is_active=False)

    # Пытаемся найти активный
    report = WeeklyFactorReport.objects.filter(
        organization=organization,
        week_start=week_start,
        is_active=True
    ).first()

    if report:
        return report

    # Если нет — создаём новый
    return WeeklyFactorReport.objects.create(
        organization=organization,
        week_start=week_start,
        week_end=week_end,
        is_active=True
    )


def parse_factor_response(text: str) -> list[dict]:
    factors = []
    current = None

    lines = text.replace("=== RESPONSE ===", "").strip().splitlines()

    for line in lines:
        line = line.strip()

        # Парсим заголовок "Фактор 1: ..."
        match_title = re.match(r"(Фактор)\s+\d+:\s+(.+)", line)
        if match_title:
            if current:
                factors.append(current)
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
        factors.append(current)

    return factors


def extract_request_ids_from_text(text):
    """
    Ищет все ID звонков в тексте по шаблону 'звонок <число>'.
    """
    matches = re.findall(r"звонок\s*(\d+)", text.lower())
    return list(map(int, matches))


def save_weekly_factors(response_text, report):
    parsed = parse_factor_response(response_text)

    for factor_data in parsed:
        title = factor_data["title"].strip()
        frequency = factor_data.get("frequency") or 0

        if frequency == 0 or not factor_data["examples"]:
            continue
        
        factor, created = WeeklyFactor.objects.update_or_create(
            report=report,
            title__iexact=title,
            defaults={"title": title, "frequency": frequency}
        )

        for example_line in factor_data["examples"]:
            example = FactorExample.objects.create(factor=factor, text=example_line)
            request_ids = extract_request_ids_from_text(example_line)

            for req_id in request_ids:
                incoming = IncomingRequest.objects.filter(id=req_id).first()
                if incoming:
                    example.incoming_requests.add(incoming)


def analyze_weekly_factors(org, specific_report=None):
    """
    Анализирует факторы за неделю для организации.
    """
    report = specific_report or get_or_create_active_weekly_factor_report(org)

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

        existing_factors = report.factors.all()

        if existing_factors.exists():
            prompt = build_prompt_with_existing_factors(existing_factors, calls_text)
        else:
            prompt = DEFAULT_WEEKLY_FACTOR_PROMPT_INITIAL + "\n\n" + calls_text

        client = init_tmodel_client(api_key=org.donkit_api_key)
        response, _, _ = send_question_to_tlite(client, prompt)
        if response:
            save_weekly_factors(response, report)

