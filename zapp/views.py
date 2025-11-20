import logging, json, urllib.parse, csv, math
from .services.context_builders import *
from .services.t_model import *
from .services.amocrm_service import *
from .services.bitrix_service import *
from .tasks import *
from .models import *

from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.db.models import Q, Prefetch, Count
from django.utils.timezone import localtime

logger = logging.getLogger(__name__)

MINIMAL_CALL_LENGTH = 30

def is_superadmin(user):
    return user.is_authenticated and user.profile.role == "superadmin"


def is_org_admin(user):
    return user.is_authenticated and user.profile.role == "admin"


def is_user(user):
    return user.is_authenticated and user.profile.role == "user"


def login_view(request):
    """
    Отображает страницу входа и обрабатывает запросы на авторизацию пользователя.
    Если авторизация успешна, перенаправляет на главную страницу.
    """
    if request.method == 'POST':
        username = request.POST.get('username')  # Получаем имя пользователя
        password = request.POST.get('password')  # Получаем пароль
        user = authenticate(request, username=username, password=password)  # Аутентификация пользователя
        if user is not None:
            login(request, user)  # Выполняем вход
            return redirect('home')  # Перенаправление на главную страницу
        else:
            messages.error(request, 'Invalid username or password')  # Сообщение об ошибке
    return render(request, 'login.html')  # Отображение страницы входа


def custom_logout_view(request):
    """
    Отображает главную страницу с данными организаций, запросов и промптов.
    Поддерживает выбор активной организации через GET-параметр `organization_id`.
    """
    logout(request)  # Завершаем сессию пользователя
    return redirect('/login/')  # Перенаправляем на страницу входа


@login_required
def stats_20_view(request):
    organization_id = request.GET.get("organization_id")
    selected_organization = Organization.objects.filter(pk=organization_id).first()

    if not selected_organization:
        return redirect("home")

    organizations = Organization.objects.all()
    return render(request, "stats_20.html", build_stats_context(request, selected_organization, organizations))


@login_required
def organization_detail(request, pk):
    """
    Отображает страницу с подробностями об организации на основе её ID.
    """
    organization = get_object_or_404(Organization, pk=pk)  # Получаем организацию или возвращаем 404
    return render(request, 'organization_detail.html', {'organization': organization})


def get_smart_page_range(page, paginator, delta=2, ends=2):
    current = page.number
    total = paginator.num_pages
    result = []

    left = range(1, min(ends + 1, total + 1))
    middle = range(max(current - delta, ends + 1), min(current + delta + 1, total - ends + 1))
    right = range(max(total - ends + 1, ends + 1), total + 1)

    last = 0
    for part in (left, middle, right):
        for num in part:
            if last and num - last > 1:
                result.append(None)  # точка
            if num not in result:
                result.append(num)
            last = num
    return result


@login_required
def home_view(request):
    organizations = Organization.objects.all()
    selected_organization = None
    related_requests = []
    prompts = []
    processed_requests = []
    total_audio_duration = 0
    criteria_page = None
    all_criteria = []
    criteria_filters = Q()

    organization_id = request.GET.get('organization_id')
    tab = request.GET.get("tab")

    if organization_id:
        selected_organization = Organization.objects.filter(pk=organization_id).first()

        # 🔒 Защита: проверяем, имеет ли пользователь доступ к этой организации
        try:
            profile = request.user.profile
            if profile.role in ["admin", "user", "employee"]:
                # Пользователь может видеть только свою организацию
                if not profile.organization or selected_organization != profile.organization:
                    return redirect(f"/?organization_id={profile.organization.id}&tab=stats20")
        except UserProfile.DoesNotExist:
            pass
    else:
        try:
            user_profile = request.user.profile
            if user_profile.role in ["admin", "user", "employee"] and user_profile.organization:
                selected_organization = user_profile.organization
                organizations = Organization.objects.filter(id=selected_organization.id)  # ограничиваем список
        except UserProfile.DoesNotExist:
            pass
        
    if not selected_organization:
        return render(request, 'index.html', {'organizations': organizations})

    # Логика вкладки "Неделя"
    if tab == "weekly":
        report_id = request.GET.get("report_id")

        active_error_report = None
        active_factor_report = None
        errors = []
        factors = []
        prev_report = None
        next_report = None

        # === WeeklyErrorReport
        if report_id:
            active_error_report = WeeklyErrorReport.objects.filter(pk=report_id, organization=selected_organization).first()
        else:
            active_error_report = WeeklyErrorReport.objects.filter(
                organization=selected_organization,
                is_active=True
            ).order_by("-created_at").first()

        # === WeeklyFactorReport (по week_start и week_end от Errors)
        if active_error_report:
            active_factor_report = WeeklyFactorReport.objects.filter(
                organization=selected_organization,
                week_start=active_error_report.week_start,
                week_end=active_error_report.week_end
            ).first()

            examples_prefetch = Prefetch(
                'examples',
                queryset=ErrorExample.objects.prefetch_related('incoming_requests')
            )
            errors = (
                WeeklyError.objects.filter(report=active_error_report)
                .annotate(example_count=Count("examples"))
                .order_by("-example_count")
                .prefetch_related(examples_prefetch)
            )

            # Загружаем факторы
            if active_factor_report:
                examples_prefetch = Prefetch(
                    'examples',
                    queryset=FactorExample.objects.prefetch_related('incoming_requests')
                )
                factors = (
                    WeeklyFactor.objects.filter(report=active_factor_report)
                    .annotate(example_count=Count("examples"))
                    .order_by("-example_count")
                    .prefetch_related(examples_prefetch)
                )

            # === Prev / Next для Errors
            prev_report = WeeklyErrorReport.objects.filter(
                organization=selected_organization,
                week_end__lt=active_error_report.week_start
            ).order_by('-week_end').first()

            next_report = WeeklyErrorReport.objects.filter(
                organization=selected_organization,
                week_start__gt=active_error_report.week_end
            ).order_by('week_start').first()

        return render(request, "index.html", {
            "organizations": organizations,
            "selected_organization": selected_organization,
            "active_error_report": active_error_report,
            "active_factor_report": active_factor_report,
            "errors": errors,
            "factors": factors,
            "prev_report": prev_report,
            "next_report": next_report,
        })
    
    # Логика "Статистика 2.0"
    if tab == "stats20":
        return render(request, 'index.html', build_stats_context(request, selected_organization, organizations))

    # Обычная домашняя логика
    total_audio_duration = selected_organization.total_audio_duration
    related_requests = list(selected_organization.requests.prefetch_related('related_s2t_requests', 'related_donkit_requests').all())
    prompts = list(selected_organization.prompts.all())

    filters = Q()
    if request.GET.get('meeting'):
        filters |= Q(criteria__meeting=True)
    if request.GET.get('questions'):
        filters |= Q(criteria__questions=True)
    if request.GET.get('positive'):
        filters |= Q(criteria__positive=True)

    processed_requests = IncomingRequest.objects.filter(
        organization=selected_organization,
        ignored=False,
        criteria__isnull=False
    ).select_related('organization')

    if filters:
        processed_requests = processed_requests.filter(filters)

    processed_requests = processed_requests.prefetch_related('criteria').order_by('-created_at')

    # processed_requests = IncomingRequest.objects.filter(
    #     organization=selected_organization,
    #     ignored=False,
    #     criteria__isnull=False
    # ).filter(filters).prefetch_related('criteria').order_by('-created_at') if filters else \
    #     IncomingRequest.objects.filter(
    #         organization=selected_organization,
    #         ignored=False,
    #         criteria__isnull=False
    #     ).prefetch_related('criteria').order_by('-created_at')

    criteria_filters = Q(incoming_request__organization=selected_organization)
    if request.GET.get('contact'):
        criteria_filters &= Q(contact__gt=0)
    if request.GET.get('needs_analysis'):
        criteria_filters &= Q(needs_analysis__gt=0)
    if request.GET.get('presentation'):
        criteria_filters &= Q(presentation__gt=0)
    if request.GET.get('persuasion'):
        criteria_filters &= Q(persuasion__gt=0)
    if request.GET.get('follow_up'):
        criteria_filters &= Q(follow_up__gt=0)

    all_criteria = list(CriteriaSteps.objects.filter(criteria_filters).order_by("-created_at"))

    page_number = request.GET.get('page', 1)
    page_obj = Paginator(related_requests, 50).get_page(page_number)
    processed_requests_page = Paginator(processed_requests, 50).get_page(page_number)
    criteria_page = Paginator(all_criteria, 50).get_page(page_number)

    for incoming_request in processed_requests:
        incoming_request.amocrm_contact_url = f"https://{incoming_request.organization.account_amocrm}.amocrm.ru/contacts/detail/{incoming_request.user_id}"

    criteria_qs = CriteriaSteps.objects.filter(criteria_filters).order_by("-created_at")

    context = {
        'organizations': organizations,
        'selected_organization': selected_organization,
        'related_requests': page_obj,
        'processed_requests': processed_requests_page,
        'criteria_page': criteria_page,
        'prompts': prompts,
        'total_audio_duration': total_audio_duration,
        'manager_chart_data': get_manager_chart_data(selected_organization),
        'deal_stage_chart': get_deal_stage_data(selected_organization),
        'objection_chart_data': get_objection_chart_data(selected_organization),
        'criteria_scores': get_criteria_scores(selected_organization, request=request),
        'criteria_icons': get_criteria_icons(),
        'smart_page_range': get_smart_page_range(page_obj, page_obj.paginator),
        'max_duration': 0,
        **get_call_stats(selected_organization)
    }

    return render(request, 'index.html', context)


@method_decorator(csrf_exempt, name='dispatch')  
class GetCallWebhook(View):
    """
    Вебхук для обработки входящих данных от amoCRM.
    Валидирует данные и направляет их в Celery задачу для дальнейшей обработки.
    """

    def post(self, request, *args, **kwargs):
        try:
            # Логируем заголовки запроса
            logger.warning(f"Заголовки запроса: {dict(request.headers)}")

            # Получаем данные запроса
            data = request.POST.dict()
            logger.warning(f"Получен запрос: {data}")

            # Проверяем наличие subdomain
            subdomain = data.get("account[subdomain]")
            if not subdomain:
                logger.warning("Запрос без поля 'account[subdomain]'.")
                return JsonResponse({"status": "error", "message": "Поле 'account[subdomain]' отсутствует."}, status=400)

            # Получаем по subdomain организацию из таблицы Organization
            organization = Organization.objects.filter(account_amocrm=subdomain).first()
            if not organization:
                logger.warning(f"Запрос от неизвестного subdomain: {subdomain}")
                return JsonResponse({"status": "ignored", "message": f"Subdomain '{subdomain}' не зарегистрирован."}, status=403)
            
            
            if organization.trial_expires_at and localtime().date() > organization.trial_expires_at:
                return JsonResponse({"status": "error", "message": "Истек срок пробного периода."})

            # Список возможных источников (контакты, сделки, компании)
            sources = ["contacts", "leads", "companies"]

            found_valid_note = False

            for source in sources:
                note_prefix = f"{source}[note][0][note]"
                note_type = data.get(f"{note_prefix}[note_type]")

                if note_type not in ["10", "11"]:
                    continue  # Пропускаем нерелевантные примечания

                # Валидное примечание найдено
                found_valid_note = True

                # Передаём в задачу Celery (вы можете передать ещё element_id, element_type, если нужно)
                process_amocrm_request.delay(data)
                break  # обрабатываем только первое подходящее примечание

            if found_valid_note:
                return JsonResponse({"status": "success", "message": "Запрос передан в обработку."}, status=200)
            else:
                logger.warning("Примечание не является аудиозаписью или не найдено. END")
                return JsonResponse({"status": "ignored", "message": "Примечание не является аудиозаписью."}, status=200)

        except Exception as e:
            logger.error(f"Ошибка обработки запроса: {str(e)}. END")
            return JsonResponse({"status": "error", "message": str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class GetCallBitrixWebhook(View):
    """
    Вебхук для обработки входящих данных из Bitrix24.
    Сначала сохраняет CALL_ID, а затем через 5 секунд делает запрос для получения CALL_RECORD_URL.
    """
    def post(self, request, *args, **kwargs):
        try:
            # Проверяем, что тело запроса не пустое
            if not request.body:
                logger.error("Bitrix24 отправил пустое тело запроса!")
                return JsonResponse({"status": "error", "message": "Empty request body. END"}, status=400)

            # Определяем формат входящих данных
            content_type = request.headers.get('Content-Type', '')

            if "application/json" in content_type:
                try:
                    data = json.loads(request.body.decode('utf-8'))
                except json.JSONDecodeError:
                    logger.error("Ошибка обработки JSON в вебхуке Bitrix24. END")
                    return JsonResponse({"status": "error", "message": "Invalid JSON format"}, status=400)

            elif "application/x-www-form-urlencoded" in content_type:
                data = urllib.parse.parse_qs(request.body.decode('utf-8'))
                data = {k: v[0] if isinstance(v, list) else v for k, v in data.items()}

            else:
                logger.error(f"Неподдерживаемый формат данных: {content_type}. END")
                return JsonResponse({"status": "error", "message": f"Unsupported content type: {content_type}"}, status=400)

            # Проверяем наличие CALL_ID
            call_id = data.get("data[CALL_ID]") or data.get("CALL_ID")
            if not call_id:
                logger.error("Вебхук не содержит CALL_ID")
                return JsonResponse({"status": "error", "message": "CALL_ID отсутствует"}, status=400)

            # Получаем значение CALL_DURATION
            call_duration_raw = data.get("data[CALL_DURATION]")

            # Проверяем проблемные сценарии
            if call_duration_raw is None or call_duration_raw == "" or not call_duration_raw.isdigit():
                call_duration = 0  # Если нет данных или некорректный формат, ставим 0
            else:
                call_duration = int(call_duration_raw)  # Безопасное преобразование

            # Определяем организацию по REST_APP_NAME или auth[domain]
            full_b24_domain = data.get("auth[domain]")

            if full_b24_domain:
                b24_domain = full_b24_domain.split('.')[0]
            else:
                b24_domain = None

            organization = Organization.objects.filter(b24_domain=b24_domain).first()

            if not organization:
                logger.warning(f"Не найдена организация для домена {b24_domain}. END")
                return JsonResponse({"status": "ignored", "message": "Организация не найдена"}, status=403)

            if organization.trial_expires_at and localtime().date() > organization.trial_expires_at:
                return JsonResponse({"status": "error", "message": "Истек срок пробного периода. END"})
            

            minimal_length = organization.minimal_call_length# or MINIMAL_CALL_LENGTH
            ignored_flag = call_duration < minimal_length

            # Получаем значение CALL_TYPE
            call_type = data.get("data[CALL_TYPE]")

            # По умолчанию считаем звонок исходящим, если CALL_TYPE не определён
            if call_type == "1" or call_type == "3":
                call_direction = "incoming"
            else:
                call_direction = "outgoing"

            # **Сохраняем входящий запрос**
            incoming_request = IncomingRequest.objects.create(
                raw_data=data,
                domain_b24=b24_domain,
                call_id_b24=call_id,
                ignored=ignored_flag,
                organization=organization,
                source="Bitrix24",
                call_direction=call_direction 
            )
            
            if ignored_flag:
                logger.warning(f"Запрос с CALL_ID {call_id} сохранён, но помечен как ignored. Длительность {call_duration} сек < MINIMAL_CALL_LENGTH сек. END")
                return JsonResponse({"status": "ignored", "message": f"Запрос с CALL_ID {call_id} сохранён, но помечен как ignored. Длительность ({call_duration} сек меньше чем минимальная"}, status=200)

            # **Запускаем Celery-задачу для получения CALL_RECORD_URL**
            get_bitrix_call_record_task.apply_async(args=[incoming_request.id], countdown=5)

            return JsonResponse({"status": "success", "message": "Запрос принят, ожидаем ссылку на запись"}, status=200)

        except Exception as e:
            logger.error(f"Ошибка обработки вебхука Bitrix24: {str(e)}. END")
            return JsonResponse({"status": "error", "message": str(e)}, status=500)
        

@login_required
def add_crm_note_view(request, incoming_request_id):
    """
    Ручная отправка примечания в amoCRM или комментария в Bitrix24.
    """
    if request.method == "POST":
        try:
            incoming_request = IncomingRequest.objects.get(id=incoming_request_id)
            organization = incoming_request.organization
            
            # Получаем последний анализ от нейросети
            donkit_request = incoming_request.related_donkit_requests.order_by('-created_at').first()
            if not donkit_request or not donkit_request.answer:
                logger.error(f"Нет доступных ответов DeepSeekV3 для запроса {incoming_request_id}. END")
                return JsonResponse({"status": "error", "message": "Нет доступных аналитических данных для отправки в CRM."})

            comment = donkit_request.answer

            # Определяем, в какую CRM отправить
            if incoming_request.source == "amoCRM":
                # Разделение ответа на аналитику и саммари
                analytics, summary = split_answer(comment)  

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
                        active_leads = get_active_leads_with_tag(incoming_request.user_id, organization)
                        for lead in active_leads:
                            add_note_to_lead.delay(organization.id, lead["id"], "**Саммари:**\n\n"+summary)
                elif incoming_request.organization.send_comments_to_amocrm and incoming_request.organization.custom_crm:
                    send_custom_crm_note(organization, incoming_request.user_id, text_to_send)

            
            elif incoming_request.source == "Bitrix24":
                add_bitrix_comment(organization.id, incoming_request.user_id_b24, comment)
            
            return JsonResponse({"status": "success", "message": "Задача на добавление примечания отправлена."})

        except IncomingRequest.DoesNotExist:
            return JsonResponse({"status": "error", "message": "Входящий запрос не найден."})
        except Exception as e:
            logger.error(f"Ошибка при отправке примечания в CRM: {str(e)}. END")
            return JsonResponse({"status": "error", "message": str(e)})

    return JsonResponse({"status": "error", "message": "Неверный метод запроса."})
    

@login_required
def send_to_transcription(request, request_id):
    """
    Направляет входящий запрос на транскрибацию.
    Создаёт Celery задачу для отправки запроса в службу Speech2Text.
    """
    if request.method == 'POST':
        try:
            incoming_request = IncomingRequest.objects.get(id=request_id)  # Получаем входящий запрос
            # Передаем ID входящего запроса в Celery задачу
            send_to_speech2text.delay(incoming_request.id)
            return JsonResponse({"status": "success", "message": "Запрос отправлен на транскрибацию"})
        except IncomingRequest.DoesNotExist:
            return JsonResponse({"status": "error", "message": "Входящий запрос не найден"})
    return JsonResponse({"status": "error", "message": "Неверный метод запроса"})


@login_required
def send_to_donkit(request, incoming_request_id):
    """
    Отправляет запрос в Deepseek с выбранным промптом.
    Если промпт не указан, используется последний добавленный.
    """
    if request.method == "POST":
        try:
            incoming_request = get_object_or_404(IncomingRequest, id=incoming_request_id)  # Получаем входящий запрос
            organization = incoming_request.organization  # Получаем организацию, связанную с запросом
            
            logger.warning(f"Полученное тело запроса для отправки в Deepseek: {request.body.decode('utf-8')}")
            
            # Обрабатываем тело запроса
            try:
                data = json.loads(request.body)  # Парсим JSON
            except json.JSONDecodeError:
                return JsonResponse({"status": "error", "message": "Некорректный JSON в теле запроса в Deepseek. END"})
            prompt_id = data.get('prompt_id')
            prompt = Prompt.objects.filter(id=prompt_id, organization=organization).first()

            if prompt_id:
                prompt = Prompt.objects.filter(id=prompt_id, organization=organization).first()
                if not prompt:
                    return JsonResponse({"status": "error", "message": "Выбранный промпт не найден для организации"})
            else:
                # Выбираем последний добавленный промпт, если ID не передан
                prompt = organization.prompts.order_by('-created_at').first()
                if not prompt:
                    return JsonResponse({"status": "error", "message": "Нет доступных промптов для организации"})

            if not prompt:
                return JsonResponse({"status": "error", "message": "Нет доступных промптов для запроса в Deepseek"})

            # Передаем задачу в Celery
            send_to_donkit_task.delay(incoming_request.id, prompt.id)
            return JsonResponse({"status": "success", "message": "Запрос отправлен в Deepseek"})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})
    else:
        logger.warning("Возникла ошибка по отправке запроса в донкит. Запрос оказался не POST")
    return JsonResponse({"status": "error", "message": "Неверный метод запроса"})
    

@login_required
def add_prompt(request):
    """
    Добавляет новый промпт для текущей организации.
    Принимает данные из формы и создаёт новый объект Prompt.
    """
    if request.method == 'POST':
        organization_id = request.POST.get('organization_id')  # Получаем ID организации
        organization = Organization.objects.get(id=organization_id)

        name = request.POST.get('name')  # Название промпта
        description = request.POST.get('description')  # Описание промпта

        # Создаем новый промпт
        Prompt.objects.create(
            name=name,
            description=description,
            organization=organization,
        )
        messages.success(request, "Промпт успешно добавлен!")  # Сообщение об успешном добавлении
        return redirect('home')
    return redirect('home')


@login_required
def export_requests_csv(request):
    organization_id = request.GET.get("organization_id")

    if not organization_id:
        return HttpResponse("Organization not specified", status=400)

    from .models import Organization
    organization = Organization.objects.filter(id=organization_id).first()
    if not organization:
        return HttpResponse("Organization not found", status=404)

    context = build_stats_context(request, organization, Organization.objects.all())
    requests = context["processed_requests"]

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="filtered_requests.csv"'

    writer = csv.writer(response)
    writer.writerow(["ID", "Дата и время", "Источник", "Сущность", "Тип звонка", "Менеджер", "Оценка"])

    for req in requests:
        # Безопасно достаём последнюю запись criteria_steps
        last_criteria = CriteriaSteps.objects.filter(incoming_request=req).order_by('-created_at').first()
        score = last_criteria.overall_score if last_criteria else "–"

        writer.writerow([
            req.id,
            req.created_at.strftime("%d.%m.%Y %H:%M"),
            req.source,
            f"{req.crm_entity_type} #{req.crm_entity_id}" if req.crm_entity_type else "–",
            req.call_direction or "–",
            req.manager.full_name if req.manager else "–",
            score
        ])

    return response


def weekly_summary_view(request):
    org_id = request.GET.get("organization_id")
    selected_organization = get_object_or_404(Organization, id=org_id)

    active_report = WeeklyReport.objects.filter(
        organization=selected_organization,
        is_active=True
    ).order_by("-created_at").first()

    insights = active_report.insights.prefetch_related("examples__incoming_requests") if active_report else []

    context = {
        "selected_organization": selected_organization,
        "active_report": active_report,
        "insights": insights,
    }
    return render(request, "weekly_summary.html", context)


