import logging, re
from openai import OpenAI
from ..models import *


# Настраиваем логгер
logger = logging.getLogger(__name__)

# Глобальная переменная для хранения клиента
client = None
old_base_url="https://api.fireworks.ai/inference/v1"


def init_tmodel_client(api_key, base_url="https://api.fireworks.ai/inference/v1"):
    """
    Инициализирует клиента OpenAI для работы с моделью DeepSeekV3.
    """
    client = OpenAI(
        base_url=base_url,
        api_key=api_key
    )
    return client


def split_answer(answer_text):
    """
    Делит текст ответа нейросети на АНАЛИТИКУ и САММАРИ по ключевому слову "Саммари:".
    """
    if not answer_text:
        return "", ""

    split_keyword = "Саммари:"

    if split_keyword in answer_text:
        parts = answer_text.split(split_keyword, 1)
        analytics = parts[0].strip()
        summary = parts[1].strip()
        return analytics, summary
    else:
        # Если "Саммари:" нет — весь текст считаем аналитикой, саммари нет
        return answer_text.strip(), ""
    

def send_question_to_tlite(client, question):
    """
    Отправляет запрос в DeepSeekV3 и возвращает обработанный ответ без форматирующих символов.
    """
    if client is None:
        return None, None, None

    try:
        # Отправка запроса к нейросети
        response = client.chat.completions.create(
            model="accounts/fireworks/models/deepseek-v3p1-terminus",
            messages=[{"role": "user", "content": question}]
        )

        # Извлекаем текст ответа
        raw_answer = response.choices[0].message.content
        tokens_used = response.usage.total_tokens

        # Очищаем ответ от форматирования
        cleaned_answer = raw_answer #clean_answer_text(raw_answer) из-за clean_answer_text удалялась важная часть текст 22.04.25г.

        return cleaned_answer, tokens_used, raw_answer

    except Exception as e:
        logger.error(f"Ошибка при запросе к DeepSeekV3: {str(e)}")
        return None, None, None


def analyze_criteria_20(donkit_response: str, incoming_request):
    """
    Анализирует ответ нейросети и сохраняет оценки по критериям (1–7)
    и итоговую оценку (overall_score) в модель CriteriaSteps.
    """
    try:
        # Только активные позиции
        active_positions = set(
            CriteriaLabel.objects
            .filter(organization=incoming_request.organization)
            .values_list("position", flat=True)
        )

        # Шаблон: "1. Установление контакта (оценка: 3)"
        pattern = r"(?P<position>\d+)\.\s*.+?\((?:оценка|общая оценка):\s*(?P<score>\d+)\)"
        matches = re.findall(pattern, donkit_response)

        scores = {}
        for pos_str, score_str in matches[:7]:
            pos = int(pos_str)
            score = int(score_str)
            if 1 <= pos <= 7 and pos in active_positions:
                scores[f"criteria_{pos}"] = score

        # Шаблон итоговой оценки: "Итоговая оценка: 9/14"
        overall_score_pattern = r"Итоговая оценка[:\s]*([\d]+)\s*/\s*[\d]+"
        overall_score_match = re.search(overall_score_pattern, donkit_response)
        if overall_score_match:
            scores["overall_score"] = int(overall_score_match.group(1))

        if not scores:
            raise ValueError("Не найдены оценки в ответе нейросети.")

        # Создаём или обновляем запись
        criteria_obj, created = CriteriaSteps.objects.get_or_create(
            incoming_request=incoming_request,
            defaults=scores
        )
        if not created:
            for field, value in scores.items():
                setattr(criteria_obj, field, value)
            criteria_obj.save()

        return criteria_obj

    except Exception as e:
        logger.error(f"Ошибка анализа критериев: {str(e)}")
        return None
 