import requests
import logging

logger = logging.getLogger(__name__)

def send_custom_crm_note(organization, external_id, text):
    """
    Отправка комментария в стороннюю CRM по кастомному API.
    """
    url = "https://crm.yarkiedeti.ru/api-aventika/notes"
    payload = {
        "id": external_id,
        "notes": text,
        "app_token": "1orko64hQI7fuY53zycaM4nEzMyvcbsW" #organization.donkit_api_key or "",  # или завести отдельное поле org.custom_crm_token
    }
    logger.warning(payload)

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"[CustomCRM] Ошибка при отправке заметки: {str(e)}")