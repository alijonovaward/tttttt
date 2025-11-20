import requests, logging, re
from celery import shared_task
from ..models import *

logger = logging.getLogger(__name__)


def call_bitrix_method(organization, api_key, method, data):
    """
    Выполняет запрос к API Bitrix24 с переданным API-ключом.

    :param organization: Объект организации, содержащий домен Bitrix24 и ID администратора.
    :param api_key: API-ключ для выполнения запроса (например, b24_api_stat или b24_api_comment).
    :param method: Метод API Bitrix24 (например, 'voximplant.statistic.get' или 'crm.timeline.comment.add').
    :param data: Данные для отправки в Bitrix24.
    :return: JSON-ответ от Bitrix24 или None в случае ошибки.
    """
    url = f"https://{organization.b24_domain}.bitrix24.ru/rest/{organization.b24_admin_id}/{api_key}/{method}"
    
    response = requests.post(url, json=data)

    if response.status_code == 200:
        return response.json()
    else:
        return None


def get_call_record_by_call_id(organization, call_id):
    """
    Возвращает данные о звонке, включая запись, по CALL_ID.
    """
    data = {
        "FILTER": {"CALL_ID": call_id},
        "SELECT": ["CALL_ID", "CALL_RECORD_URL", "CALL_DURATION"]
    }

    result = call_bitrix_method(organization, organization.b24_api_stat, "voximplant.statistic.get", data)

    if result and "result" in result and isinstance(result["result"], list) and len(result["result"]) > 0:
        return result["result"][0]  # Берем первую запись (она единственная)
    else:
        return None


def get_lead_by_company_id(organization, company_id):
    """
    Получает последний активный лид, связанный с компанией.
    Фильтрует по COMPANY_ID и исключает лиды со статусами 'CONVERTED' и 'JUNK'.
    """
    method = "crm.lead.list"
    data = {
        "filter": {
            "COMPANY_ID": company_id,
            "!STATUS_ID": ["CONVERTED", "JUNK"]
        },
        "select": ["ID", "TITLE", "STATUS_ID"],
        "order": {"ID": "DESC"}  # Берем последний актуальный лид
    }

    result = call_bitrix_method(organization, organization.b24_api_leads, method, data)

    if result and "result" in result and isinstance(result["result"], list) and len(result["result"]) > 0:
        return result["result"][0]  # Берем самый свежий лид
    else:
        return None
    

@shared_task
def add_bitrix_comment(organization_id, crm_entity_type, crm_entity_id, comment):
    """
    Асинхронно добавляет комментарий к контакту в Bitrix24.
    Используется Celery для выполнения фоновой задачи.

    :param organization_id: ID организации в БД.
    :param crm_entity_type: Тип сущности в Bitrix24 (CONTACT, LEAD, COMPANY).
    :param crm_entity_id: ID сущности в Bitrix24.
    :param comment: Полный текст комментария (из которого берем только часть после "8.")
    """
    try:
        organization = Organization.objects.get(id=organization_id)
    except Organization.DoesNotExist:
        return
    
    # Извлекаем текст после "8."
    match = re.search(r"8\.\s*(.*)", comment, re.DOTALL)
    filtered_comment = match.group(1).strip() if match else comment  # Если не найдено, оставляем оригинальный текст

    if not filtered_comment:
        return
    
    method = "crm.timeline.comment.add"
    data = {
        "fields": {
            "ENTITY_ID": crm_entity_id,
            "ENTITY_TYPE": crm_entity_type,
            "COMMENT": filtered_comment,
            "AUTHOR_ID": organization.b24_admin_id
        }
    }

    response = call_bitrix_method(organization, organization.b24_api_comment, method, data)
    
    if response and "result" in response:
        return response
    else:
        return None
    

def get_bitrix_lead_details(organization, lead_id):
    """
    Получает данные о сделке (лиде) в Bitrix24.
    """
    try:
        method = "crm.lead.get"
        data = {
            "ID": lead_id
        }

        result = call_bitrix_method(organization, organization.b24_api_leads, method, data)

        if result and "result" in result:
            return result["result"].get("STATUS_ID", "").strip()  # Возвращаем JSON с деталями лида
        else:
            return None
    except Exception as e:
        return None