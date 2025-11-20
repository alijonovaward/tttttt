import requests, logging, json
from datetime import datetime
from celery import shared_task
from ..models import *

logger = logging.getLogger(__name__)


def get_contact_with_leads(contact_id, organization):
    """
    Получает данные контакта вместе с привязанными сделками.
    """
    try:
        url = f"https://{organization.account_amocrm}.amocrm.ru/api/v4/contacts/{contact_id}?with=leads"
        headers = {
            "Authorization": f"Bearer {organization.bearer_amocrm}"
        }
        response = requests.get(url, headers=headers, timeout=(10, 60))
        if response.status_code != 200:
            return None

        return response.json()
    except Exception as e:
        logger.error(f"Ошибка при получении данных контакта {contact_id}: {str(e)}")
        return None


def get_lead_tags(subdomain, lead_id, token):
    """
    Получение тегов сделки через данные сделки.
    """
    try:
        url = f"https://{subdomain}.amocrm.ru/api/v4/leads/{lead_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        response = requests.get(url, headers=headers, timeout=(10, 60))

        if response.status_code == 200:
            # Извлекаем теги из ответа
            lead_data = response.json()
            return lead_data.get('_embedded', {}).get('tags', [])
        else:
            return []

    except Exception as e:
        logger.error(f"Ошибка при выполнении запроса данных сделки {lead_id}: {str(e)}")
        return []


def has_lead_tag(lead_id, organization, tag_name):
    """
    Проверяет, есть ли у сделки указанный тег.
    """
    try:
        # Передаем subdomain и token в get_lead_tags
        tags = get_lead_tags(
            subdomain=organization.account_amocrm,
            lead_id=lead_id,
            token=organization.bearer_amocrm
        )
        if not tags or not tag_name:
            return False

        # Приводим все теги и искомый тег к нижнему регистру
        tag_name_lower = tag_name.lower()
        return any(tag["name"].lower() == tag_name_lower for tag in tags)
    except Exception as e:
        logger.error(f"Ошибка при проверке тега сделки {lead_id}: {str(e)}")
        return False
    

def get_active_leads_with_tag(contact_id, organization, tag_name=None):
    """
    Получает активные сделки контакта.
    Если указан тег, фильтрует сделки по наличию этого тега.
    Если тег не указан, возвращает все активные сделки.
    """
    try:
        # Получаем данные контакта с привязанными сделками
        contact_data = get_contact_with_leads(contact_id, organization)
        if not contact_data:
            return []

        # Извлекаем сделки
        leads = contact_data.get("_embedded", {}).get("leads", [])
        active_leads = [lead for lead in leads if not lead.get("is_deleted") and lead.get("status_id") not in {142, 143}]

        if not tag_name:
                return active_leads  # Если тег не указан — возвращаем все активные лиды
        
        # Проверяем наличие указанного тега
        active_leads_with_tag = []
        for lead in active_leads:
            if has_lead_tag(lead["id"], organization, tag_name):
                active_leads_with_tag.append(lead)

        return active_leads_with_tag
    except Exception as e:
        logger.error(f"Ошибка при получении активных сделок с тегом {tag_name} для контакта {contact_id}: {str(e)}")
        return []


@shared_task
def add_amo_note(organization_id, user_id, comment):
    """
    Асинхронно добавляет примечание к контакту в amoCRM.
    Использует Celery для фоновой задачи.

    :param organization: Оганизация в БД.
    :param user_id: ID контакта в amoCRM.
    :param comment: Текст примечания.
    """
    
    organization = Organization.objects.get(id=organization_id)
    auth_token = organization.bearer_amocrm

    if not auth_token:
        return None

    url = f"https://{organization.account_amocrm}.amocrm.ru/api/v4/contacts/{user_id}/notes"
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }
    data = [
        {
            "entity_id": user_id,
            "note_type": "common",
            "params": {
                "text": comment
            }
        }
    ]

    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 200:
        return response.json()
    else:
        logger.error(f"Ошибка добавления примечания в amoCRM: {response.status_code}, {response.text}")


@shared_task
def add_note_to_lead(organization_id, lead_id, comment):
    """
    Добавляет примечание к сделке в amoCRM.
    """
    try:
        organization = Organization.objects.get(id=organization_id)
        auth_token = organization.bearer_amocrm

        if not auth_token:
            return None

        url = f"https://{organization.account_amocrm}.amocrm.ru/api/v4/leads/{lead_id}/notes"
        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
        data = [
            {
                "entity_id": lead_id,
                "note_type": "common",
                "params": {
                    "text": comment
                }
            }
        ]

        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            return response.json()

    except Exception as e:
        logger.error(f"Ошибка при добавлении примечания в сделку {lead_id}: {str(e)}")


# Исключаем завершенные сделки (142 - успешные, 143 - неуспешные)
EXCLUDED_STATUSES = {142, 143}

def get_latest_active_lead(contact_id, organization):
    """
    Получает последнюю активную сделку (лид) для контакта в amoCRM.

    :param contact_id: ID контакта в amoCRM.
    :param organization: Организация (модель Organization), откуда берем API-ключ.
    :return: ID последней активной сделки или None, если сделок нет.
    """
    try:
        base_url = f"https://{organization.account_amocrm}.amocrm.ru"
        contact_url = f"{base_url}/api/v4/contacts/{contact_id}?with=leads"
        headers = {
            "Authorization": f"Bearer {organization.bearer_amocrm}"
        }

        # Запрашиваем контакт и связанные сделки
        response = requests.get(contact_url, headers=headers, timeout=(10, 60))
        if response.status_code != 200:
            return None

        contact_data = response.json()

        # Проверяем, есть ли сделки у контакта
        linked_leads = contact_data.get("_embedded", {}).get("leads", [])
        if not linked_leads:
            return None

        latest_lead = None

        # Перебираем все сделки контакта и выбираем самую актуальную
        for lead in linked_leads:
            lead_id = lead["id"]
            lead_url = f"{base_url}/api/v4/leads/{lead_id}"
            lead_response = requests.get(lead_url, headers=headers, timeout=(10, 60))

            if lead_response.status_code != 200:
                continue  # Пропускаем ошибочную сделку

            lead_data = lead_response.json()
            status_id = lead_data.get("status_id")

            # Проверяем, что статус сделки не находится в исключенных
            if status_id in EXCLUDED_STATUSES:
                continue

            # Берем дату создания сделки
            created_at = lead_data.get("created_at")
            if created_at:
                created_at = datetime.fromtimestamp(created_at)  # Преобразуем timestamp в дату

                # Сравниваем с последней найденной активной сделкой
                if not latest_lead or created_at > latest_lead["created_at"]:
                    latest_lead = {
                        "id": lead_id,
                        "name": lead_data.get("name"),
                        "status_id": status_id,
                        "created_at": created_at
                    }

        if latest_lead:
            return latest_lead["id"]
        else:
            return None

    except Exception as e:
        logger.error(f"Ошибка при получении активного лида для контакта {contact_id}: {str(e)}")
        return None


def get_lead_details(lead_id, organization):
    """
    Получает данные о сделке (лиде) по ID из amoCRM.
    """
    try:
        base_url = f"https://{organization.account_amocrm}.amocrm.ru"
        lead_url = f"{base_url}/api/v4/leads/{lead_id}"
        lead_url += f"?with=contacts"
        headers = {
            "Authorization": f"Bearer {organization.bearer_amocrm}"
        }

        response = requests.get(lead_url, headers=headers, timeout=(10, 60))
        if response.status_code != 200:
            return None

        return response.json()  # Возвращаем JSON-объект с данными о сделке
    except Exception as e:
        logger.error(f"Ошибка при запросе данных сделки {lead_id}: {str(e)}")
        return None
    

def get_amo_lead_statuses(organization):
    """
    Получает список статусов сделок из amoCRM.
    """
    try:
        url = f"https://{organization.account_amocrm}.amocrm.ru/api/v4/leads/pipelines"
        headers = {"Authorization": f"Bearer {organization.bearer_amocrm}"}
        
        response = requests.get(url, headers=headers, timeout=(10, 60))
        if response.status_code != 200:
            return {}

        pipelines = response.json().get("_embedded", {}).get("pipelines", [])
        status_mapping = {}

        for pipeline in pipelines:
            statuses = pipeline.get("_embedded", {}).get("statuses", [])
            for status in statuses:
                status_mapping[str(status["id"])] = status["name"]  # ID в строку

        return status_mapping

    except Exception as e:
        logger.error(f"Ошибка при запросе статусов amoCRM: {str(e)}")
        return {}
    

def get_note_text_by_id(note_id, element_id, element_type, organization):
    """
    Получает данные примечания по ID через API amoCRM.
    Возвращает объект dict с полями note_type и params.
    """
    try:
        entity_map = {
            "1": "contacts",
            "2": "leads",
            "3": "companies",
            "12": "customers",
            "13": "tasks",
        }

        entity_type = entity_map.get(str(element_type))
        if not entity_type:
            return {}

        url = f"https://{organization.account_amocrm}.amocrm.ru/api/v4/{entity_type}/{element_id}/notes/{note_id}"

        headers = {
            "Authorization": f"Bearer {organization.bearer_amocrm}"
        }

        response = requests.get(url, headers=headers, timeout=(10, 60))

        if response.status_code != 200:
            return {}

        json_data = response.json()

        return json_data

    except Exception as e:
        logger.error(f"Ошибка при получении данных примечания {note_id}: {str(e)}")
        return {}
    

def fetch_and_create_managers(organization):
    """
    Получает всех АКТИВНЫХ пользователей amoCRM и создает объекты Manager.
    """
    try:
        url = f"https://{organization.account_amocrm}.amocrm.ru/api/v4/users"
        headers = {
            "Authorization": f"Bearer {organization.bearer_amocrm}"
        }

        response = requests.get(url, headers=headers, timeout=(10, 60))

        if response.status_code != 200:
            return

        users = response.json().get("_embedded", {}).get("users", [])

        created = 0

        for user in users:
            rights = user.get("rights", {})
            is_active = rights.get("is_active", False)
            user_id = user.get("id")
            name = user.get("name")

            if not is_active:
                continue

            user_id = user.get("id")
            name = user.get("name")

            if not user_id or not name:
                continue

            # Создаем менеджера, если еще не создан
            manager_obj, is_created = Manager.objects.get_or_create(
                organization=organization,
                manager_id_crm=str(user_id),  # Сохраняем ID как строку для универсальности
                defaults={"full_name": name}
            )
            if is_created:
                created += 1

    except Exception as e:
        logger.error(f"Ошибка при создании менеджеров из amoCRM: {str(e)}")


def assign_managers_to_requests():
    updated = 0

    for req in IncomingRequest.objects.filter(manager__isnull=True):
        raw = req.raw_data
        # Вытаскиваем created_by
        created_by = raw.get("contacts[note][0][note][created_by]")
        if not created_by:
            continue

        manager = Manager.objects.filter(manager_id_crm=str(created_by), organization=req.organization).first()
        if manager:
            req.manager = manager
            req.save()
            updated += 1