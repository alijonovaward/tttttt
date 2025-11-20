import json, requests, logging
from datetime import datetime
from celery import shared_task
from .models import *
from .services.t_model import *
from .services.pydub import *
from .services.bitrix_service import *
from .services.amocrm_service import *
from .services.weekly_reports import *
from .services.weekly_errors import *
from .services.weekly_factors import *
from .services.custom_crm_service import *

logger = logging.getLogger(__name__)

MINIMAL_CALL_LENGTH = 30
MIN_TRANSCRIBATION_TEXT_LENGTH = 100
MAX_NUMBER_OF_RETRY_TO_GET_CALL_URL = 50

@shared_task
def process_amocrm_request(data):
    """
    Обрабатывает данные из входящего вебхука amoCRM, включая contacts, leads и companies.
    """
    try:
        subdomain = data.get("account[subdomain]") 
        organization = Organization.objects.filter(account_amocrm=subdomain).first()

        if organization.custom_crm:
            # Извлекаем note
            note_id = data.get("contacts[note][0][note][id]")
            note_text_raw = data.get("contacts[note][0][note][text]")
            note_data = {}

            try:
                note_data = json.loads(note_text_raw or "{}")
            except json.JSONDecodeError:
                logger.warning(f"Не удалось распарсить note_text: {note_text_raw}")
            
            audio_link = note_data.get("LINK")
            client_phone = (note_data.get("PHONE") or "").split(",")[0].strip()
            created_by = note_data.get("created_by")

            audio_duration = get_audio_duration(audio_link) if audio_link else 0
            minimal_length = organization.minimal_call_length or MINIMAL_CALL_LENGTH
            ignored_flag = audio_duration < minimal_length

            call_direction = "outgoing"
            if (note_data.get("DIRECTION") or "").lower() == "incoming":
                call_direction = "incoming"

            manager = None
            if created_by:
                manager = Manager.objects.filter(manager_id_crm=created_by, organization=organization).first()

            incoming_request = IncomingRequest.objects.create(
                raw_data=data,
                domain=subdomain,
                ignored=ignored_flag,
                note_id=note_id,
                organization=organization,
                call_direction=call_direction,
                audio_link=audio_link,
                audio_duration=audio_duration,
                source="amoCRM-custom",
                client_phone=client_phone,
                manager=manager
            )

            if audio_link:
                send_to_speech2text.delay(incoming_request.id)

            return {"status": "success", "message": "Запрос успешно обработан"}

        def extract_note_info(data):
            """
            Универсальный парсер примечаний от amoCRM для contacts, leads, companies.
            """
            sources = {
                "contacts": "contacts[note][0][note]",
                "leads": "leads[note][0][note]",
                "companies": "contacts[note][0][note]"  # компании идут с тем же префиксом, что и контакты
            }

            for source, prefix in sources.items():
                note_type = data.get(f"{prefix}[note_type]")
                element_type = data.get(f"{prefix}[element_type]")
                if note_type in ["10", "11"]:
                    # Для компаний убеждаемся, что element_type = 3
                    if source == "companies" and element_type != "3":
                        continue
                    return {
                        "source": source,
                        "note_type": note_type,
                        "element_id": data.get(f"{prefix}[element_id]"),
                        "element_type": element_type,
                        "note_id": data.get(f"{prefix}[id]"),
                        "note_text": data.get(f"{prefix}[text]"),
                        "prefix": prefix
                    }
            return None

        note_info = extract_note_info(data)
        if not note_info:
            return {"status": "ignored", "message": "Нет допустимого звонка"}

        # Проверка обязательного поля в корневом data
        if "account[subdomain]" not in data:
            return {"status": "ignored", "message": "Нет поля account[subdomain]"}

        # Проверка обязательных полей в note_info
        for field in ["element_id", "note_id", "note_text"]:
            if not note_info.get(field):
                return {"status": "ignored", "message": f"Нет поля {field}"}

        subdomain = data["account[subdomain]"]
        element_id = note_info["element_id"]
        note_id = note_info["note_id"]
        note_text = note_info["note_text"]
        element_type = note_info["element_type"]

        # Проверка существования организации
        if not organization:
            return {"status": "ignored", "message": f"Не найдена организация {subdomain}"}

        # Парсинг note_text
        try:
            note_data = json.loads(note_text)
        except json.JSONDecodeError as e:
            return {"status": "ignored", "message": "Ошибка парсинга JSON"}

        audio_link = note_data.get("LINK")

        client_phone = note_data.get("PHONE", "").split(",")[0].strip()
        created_by = note_data.get("created_by")

        audio_duration = get_audio_duration(audio_link)
        minimal_length = organization.minimal_call_length
        ignored_flag = audio_duration < minimal_length

        manager = Manager.objects.filter(manager_id_crm=created_by, organization=organization).first()

        # Получение типа звонка
        note_info_amocrm = get_note_text_by_id(
            note_id=note_id,
            element_id=element_id,
            element_type=element_type,
            organization=organization
        )

        call_direction = "outgoing"
        if note_info_amocrm.get("note_type") == "call_in":
            call_direction = "incoming"

        # Сохраняем запрос
        incoming_request = IncomingRequest.objects.create(
            raw_data=data,
            domain=subdomain,
            ignored=ignored_flag,
            note_id=note_id,
            organization=organization,
            call_direction=call_direction,
            audio_link=audio_link,
            audio_duration=audio_duration,
            source="amoCRM",
            client_phone=client_phone,
            manager=manager,
        )

        if ignored_flag:
            return {"status": "ignored", "message": "Аудио слишком короткое"}

        # Обработка только для element_type = 1 (контакт)
        if element_type == "1":
            incoming_request.user_id = element_id
            incoming_request.save()
            contact_data = get_contact_with_leads(element_id, organization)

            if contact_data and "_embedded" in contact_data and "leads" in contact_data["_embedded"]:
                lead_id = get_latest_active_lead(element_id, organization)

                if lead_id:
                    deal_data = get_lead_details(lead_id, organization)
                    deal_status = deal_data.get("status_id") if deal_data else None
                    status_mapping = get_amo_lead_statuses(organization)
                    status_text = status_mapping.get(str(deal_status), f"Неизвестный статус ({deal_status})")

                    existing_deal = DealStage.objects.filter(deal_id_crm=lead_id, organization=organization).first()
                    if not existing_deal:
                        existing_deal = DealStage.objects.create(
                            deal_id_crm=lead_id,
                            organization=organization,
                            crm_type="amoCRM",
                            deal_type="first",
                            status=status_text
                        )
                    else:
                        if deal_status and existing_deal.status != deal_status:
                            existing_deal.status = deal_status
                            existing_deal.save()

                    incoming_request.deal_stages.add(existing_deal)
                    incoming_request.save()
        elif element_type == "2":
            # Прямая работа со сделкой, указанной в примечании
            lead_id = element_id

            # Получаем данные сделки
            deal_data = get_lead_details(lead_id, organization)
            deal_status = deal_data.get("status_id") if deal_data else None

            # Получаем текстовое описание статуса
            status_mapping = get_amo_lead_statuses(organization)
            status_text = status_mapping.get(str(deal_status), f"Неизвестный статус ({deal_status})")

            # Пытаемся найти сделку в БД
            existing_deal = DealStage.objects.filter(deal_id_crm=lead_id, organization=organization).first()

            if not existing_deal:
                # Если сделки нет — создаём новую
                existing_deal = DealStage.objects.create(
                    deal_id_crm=lead_id,
                    organization=organization,
                    crm_type="amoCRM",
                    deal_type="first",
                    status=status_text
                )
            else:
                # Если уже есть — обновляем статус при необходимости
                if deal_status and existing_deal.status != deal_status:
                    existing_deal.status = deal_status
                    existing_deal.save()

            # 🔍 Получаем contact_id первого контакта
            contact_id = None
            if deal_data:
                contacts = deal_data.get("_embedded", {}).get("contacts", [])
                if contacts:
                    contact_id = contacts[0].get("id")

            if contact_id:
                incoming_request.user_id = str(contact_id)

            # Привязываем звонок к этой сделке
            incoming_request.deal_stages.add(existing_deal)
            incoming_request.save()

        # Отправляем на транскрибацию
        if audio_link:
            send_to_speech2text.delay(incoming_request.id)

        return {"status": "success", "message": "Запрос успешно обработан"}

    except Exception as e:
        logger.error(f"Ошибка в process_amocrm_request: {str(e)}")
        raise


@shared_task(bind=True, max_retries=MAX_NUMBER_OF_RETRY_TO_GET_CALL_URL)
def get_bitrix_call_record_task(self, incoming_request_id, attempt=1):
    """
    Запрашивает CALL_RECORD_URL у Bitrix24, привязывает менеджера, телефон и сделку.
    Повторные попытки с увеличением задержки.
    """
    try:
        incoming_request = IncomingRequest.objects.get(id=incoming_request_id)
        call_id = incoming_request.call_id_b24
        organization = incoming_request.organization

        if not organization.b24_api_stat:
            return {"status": "error", "message": "API-ключ Bitrix24 отсутствует"}

        # Запрашиваем информацию о звонке
        call_data = get_call_record_by_call_id(organization, call_id)

        if call_data and call_data.get("CALL_RECORD_URL"):
            # Сохраняем данные звонка
            incoming_request.audio_link = call_data["CALL_RECORD_URL"]
            incoming_request.audio_duration = int(call_data.get("CALL_DURATION", 0))
            incoming_request.crm_entity_type = call_data.get("CRM_ENTITY_TYPE")
            incoming_request.crm_entity_id = call_data.get("CRM_ENTITY_ID")
            incoming_request.client_phone = call_data.get("PHONE_NUMBER", "").strip()

            # Привязка менеджера
            portal_user_id = call_data.get("PORTAL_USER_ID")
            if portal_user_id:
                manager = Manager.objects.filter(manager_id_crm=str(portal_user_id), organization=organization).first()
                if manager:
                    incoming_request.manager = manager

            # Проверяем, существует ли уже сделка в БД
            existing_deal_stage = None
            if incoming_request.crm_entity_type == "LEAD":
                existing_deal_stage = DealStage.objects.filter(
                    organization=organization,
                    crm_type="Bitrix24",
                    deal_id_crm=incoming_request.crm_entity_id
                ).first()

                if not existing_deal_stage:
                    # Получаем статус сделки
                    deal_status = get_bitrix_lead_details(organization, incoming_request.crm_entity_id)
                    #deal_status = deal_data.get("STATUS_ID") if deal_data else "Неизвестный статус"

                    existing_deal_stage = DealStage.objects.create(
                        organization=organization,
                        crm_type="Bitrix24",
                        deal_id_crm=incoming_request.crm_entity_id,
                        deal_type="first",
                        status=deal_status  # Сохраняем статус сделки
                    )
                else:
                    # Обновляем статус сделки
                    deal_status = get_bitrix_lead_details(organization, incoming_request.crm_entity_id)
                    #deal_status = deal_data.get("STATUS_ID") if deal_data else "Неизвестный статус"
                    if deal_status and existing_deal_stage.status != deal_status:
                        existing_deal_stage.status = deal_status
                        existing_deal_stage.save()

            # Привязываем входящий запрос к сделке
            if existing_deal_stage:
                incoming_request.deal_stages.add(existing_deal_stage)
                incoming_request.save()

            incoming_request.save()

            # Запускаем транскрибацию
            send_to_speech2text.delay(incoming_request.id)

        else:
            countdown = 5 if attempt < 10 else 10  # Первые 10 попыток с задержкой 5 сек, затем 10 сек
            if attempt < MAX_NUMBER_OF_RETRY_TO_GET_CALL_URL:
                raise self.retry(exc=Exception("Запись не найдена"), countdown=countdown)

    except Exception as e:
        logger.error(f"Ошибка при обработке звонка Bitrix24: {str(e)}")


@shared_task
def send_to_speech2text(incoming_request_id):
    """
    Отправляет аудиофайл, связанный с входящим запросом, на сервис Speech2Text.
    """
    try:
        incoming_request = IncomingRequest.objects.get(id=incoming_request_id)
        audio_link = incoming_request.audio_link
        organization = incoming_request.organization

        # Проверяем наличие API-ключа для Speech2Text
        s2t_api_key = organization.s2t_api_key
        if not s2t_api_key:
            return {"status": "error", "message": "API-ключ Speech2Text отсутствует"}

        # Формируем запрос
        url = "https://speech2text.ru/api/recognitions/task/link"
        headers = {"Content-Type":"application/json"}
        data = {"lang": "ru", "url": audio_link, "speakers": 2, "multi_channel": 1}
        response = requests.post(f"{url}?api-key={s2t_api_key}", headers=headers, json=data)

        # Обрабатываем ответ от Speech2Text
        if response.status_code == 201:
            response_data = response.json()
            task_id = response_data["id"]
            status_description = response_data["status"]["description"]

            # Сохраняем задачу в БД
            s2t_request = S2TRequest.objects.create(
                incoming_request=incoming_request,
                organization=organization,
                task_id=task_id,
                status=status_description,
                audio_link=audio_link,
            )

            if response_data.get("status", {}).get("code") == 200:
                result_links = response_data.get("result", {})
                s2t_request.txt_result_link = result_links.get("txt")
                s2t_request.transcribed_text = requests.get(result_links["txt"]+"?api-key="+s2t_api_key).text

                # Автоматически отправляем запрос в Donkit
                incoming_request = s2t_request.incoming_request
                prompt = organization.prompts.order_by('-created_at').first()
                send_to_donkit_task.delay(incoming_request.id, prompt.id if prompt else None)

                s2t_request.save()

    except Exception as e:
        logger.error(f"Ошибка при отправке на транскрибацию: {str(e)}")


@shared_task
def check_transcription_status(task_id):
    """
    еряет статус задачи в Speech2Text и сохраняет результаты.
    """
    try:
        s2t_request = S2TRequest.objects.get(task_id=task_id)
        organization = s2t_request.organization
        s2t_api_key = organization.s2t_api_key

        # Проверяем статус задачи
        url = f"https://speech2text.ru/api/recognitions/{task_id}"
        response = requests.get(f"{url}?api-key={s2t_api_key}")

        if response.status_code == 200:
            response_data = response.json()
            status = response_data.get("status", {}).get("description", "unknown")
            s2t_request.status = status

            # Если задача завершена, сохраняем текст
            if response_data.get("status", {}).get("code") == 200:
                result_links = response_data.get("result", {})
                s2t_request.txt_result_link = result_links.get("txt")
                s2t_request.transcribed_text = requests.get(result_links["txt"]+"?api-key="+s2t_api_key).text

                # Автоматически отправляем запрос в Donkit
                if not s2t_request.incoming_request:
                    logger.error(f"Ошибка привязки S2TRequest к IncomingRequest {incoming_request.id}")
                else:
                    incoming_request = s2t_request.incoming_request
                    prompt = organization.prompts.order_by('-created_at').first()
                    send_to_donkit_task.delay(incoming_request.id, prompt.id if prompt else None)
            
            s2t_request.save()

    except Exception as e:
        logger.error(f"Ошибка при проверке статуса транскрибации: {str(e)}")


@shared_task
def schedule_transcription_checks():
    """
    Проверяет статус всех запросов Speech2Text, которые находятся в состоянии ожидания или обработки.
    Если статус задания меняется на завершённое, обновляет записи в базе данных.
    """
    # Ищем все запросы со статусом, указывающим на ожидание или обработку
    pending_requests = S2TRequest.objects.filter(status__in=["Задание создано", "В очереди на распознание", "Процесс получения файла"])

    if not pending_requests.exists():
        return

    # Перебираем все найденные запросы и добавляем их в Celery очередь для проверки
    for request in pending_requests:
        S2TRequest.objects.filter(id=request.id).update(status="Распознается...")
        check_transcription_status.delay(request.task_id)


@shared_task
def send_to_donkit_task(incoming_request_id, prompt_id=None):
    """
    Отправляет запрос в DeepSeekV3.
    Если промпт не указан, используется последний добавленный промпт.
    """
    try:
        incoming_request = IncomingRequest.objects.get(id=incoming_request_id)
        organization = incoming_request.organization

        # Получаем промпт
        if prompt_id:
            prompt = Prompt.objects.get(id=prompt_id, organization=organization)
        else:
            prompt = organization.prompts.order_by('-created_at').first()

        if not prompt:
            return
        
        # Получаем текст транскрибации
        latest_s2t_request = incoming_request.related_s2t_requests.order_by('-created_at').first()
        transcribed_text = latest_s2t_request.transcribed_text if latest_s2t_request else ""

        # Проверка длины текста
        if len(transcribed_text) < MIN_TRANSCRIBATION_TEXT_LENGTH:
            return {"status": "skipped", "message": "Текст слишком короткий для отправки в DeepSeekV3"}

        # Авторизация в DeepSeekV3
        client = init_tmodel_client(api_key=organization.donkit_api_key)

        # Формируем запрос
        question = f"{prompt.description}\n\n{transcribed_text}"

        # Отправляем запрос в DeepSeekV3
        answer, tokens_used, raw_answer = send_question_to_tlite(client, question)
        if not answer:
            return
        
        # Успешная обработка: обновляем общий счётчик
        organization.total_audio_duration += incoming_request.audio_duration
        organization.save()

        # Сохраняем результат в DonkitRequest
        donkit_request = DonkitRequest.objects.create(
            incoming_request=incoming_request,
            organization=organization,
            chat_id=0,
            status="done",
            raw_data = raw_answer,
            question=question,
            answer=answer,
            tokens_used=tokens_used,  
            prompt=prompt  
        )

        # Анализируем критерии
        criteria = analyze_criteria_20(answer, incoming_request)
        # отладка критериев
        if criteria:
            logger.info(f"Критерии успешно сохранены для запроса {incoming_request.id}")
        else:
            logger.info(f"Критерии не были определены для запроса {incoming_request.id}")


        # Определяем, куда отправлять результат — amoCRM или Bitrix24
        if incoming_request.source == "amoCRM":
            # Добавляем текст транскрибации в конец ответа
            latest_s2t_request = incoming_request.related_s2t_requests.order_by('-created_at').first()

            # Разделение ответа на аналитику и саммари
            analytics, summary = split_answer(answer)  # тут функция разберет ответ

            # Отправка в контакт
            text_to_send = ""
            if organization.comment_type == 1:
                text_to_send = analytics
            elif organization.comment_type == 2:
                text_to_send = "**Саммари:**\n\n"+summary
                if summary == "":
                    return
            elif organization.comment_type == 3:
                text_to_send = analytics + "\n\n**Саммари:**\n\n" + summary


            if incoming_request.organization.send_comments_to_amocrm and not incoming_request.organization.custom_crm:
                add_amo_note.delay(incoming_request.organization.id, incoming_request.user_id, text_to_send)
                if organization.summary_to_lead and summary != "":
                    if text_to_send == "**Саммари:**\n\n":
                        return
                    active_leads = get_active_leads_with_tag(incoming_request.user_id, organization)
                    for lead in active_leads:
                        add_note_to_lead.delay(organization.id, lead["id"], "**Саммари:**\n\n"+summary)
            elif incoming_request.organization.send_comments_to_amocrm and incoming_request.organization.custom_crm:
                send_custom_crm_note(organization, incoming_request.user_id, text_to_send)


        elif incoming_request.source == "Bitrix24":
            add_bitrix_comment.delay(incoming_request.organization.id, incoming_request.crm_entity_type, incoming_request.crm_entity_id, answer)

        elif incoming_request.source == "amoCRM-custom":
            # Добавляем текст транскрибации в конец ответа
            latest_s2t_request = incoming_request.related_s2t_requests.order_by('-created_at').first()

            # Разделение ответа на аналитику и саммари
            analytics, summary = split_answer(answer)  # тут функция разберет ответ

            # Отправка в контакт
            text_to_send = ""
            if organization.comment_type == 1:
                text_to_send = analytics
            elif organization.comment_type == 2:
                text_to_send = "**Саммари:**\n\n"+summary
                if summary == "":
                    return
            elif organization.comment_type == 3:
                text_to_send = analytics + "\n\n**Саммари:**\n\n" + summary
            
            logger.warning("===============================================")
            
            if incoming_request.organization.send_comments_to_amocrm:
                send_custom_crm_note(organization, incoming_request.note_id, text_to_send)

    except Exception as e:
        logger.error(f"Ошибка в Celery задаче отправки в DeepSeekV3: {str(e)}")


@shared_task
def update_deal_statuses():
    """
    Проверяет статус сделок в CRM (Bitrix24 и amoCRM) и обновляет их в БД, если они изменились.
    Запускается раз в сутки через Celery Beat.
    """
    deals = DealStage.objects.all()

    for deal in deals:
        if deal.crm_type == "Bitrix24":
            new_status = get_bitrix_lead_details(deal.organization, deal.deal_id_crm)
        elif deal.crm_type == "amoCRM":
            lead_data = get_lead_details(deal.deal_id_crm, deal.organization)  # Переиспользуем функцию
            if lead_data:
                status_id = str(lead_data.get("status_id"))
                status_mapping = get_amo_lead_statuses(deal.organization)  # Получаем соответствие ID -> название
                new_status = status_mapping.get(status_id, f"Неизвестный статус ({status_id})")
        else:
            continue

        if new_status and new_status != deal.status:
            deal.status = new_status
            deal.updated_at = datetime.now()
            deal.save()


@shared_task
def generate_weekly_insights_for_all():
    for org in Organization.objects.all():
        analyze_weekly_errors(org)
        analyze_weekly_factors(org)


@shared_task
def generate_weekly_reports_for_all():
    for org in Organization.objects.all():
        get_or_create_active_weekly_error_report(org)
        get_or_create_active_weekly_factor_report(org)
        