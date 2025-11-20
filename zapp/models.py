from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('superadmin', 'Суперадмин'),
        ('admin', 'Администратор организации'),
        ('user', 'Пользователь'),
        ('employee', 'сотрудник')
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user')
    organization = models.ForeignKey('Organization', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"
    

class Organization(models.Model):
    """
    Организация, связанная с учетной записью amoCRM и используемыми API-ключами.
    
    Атрибуты:
        name (str): Название организации.
        short_description (str): Краткое описание организации.
        account_amocrm (str): Учетная запись amoCRM.
        bearer_amocrm (str): Токен аутентификации amoCRM.
        b24_api_stat (str): API статистики в Bitrix24.
        b24_api_comment (str): API комментариев в Bitrix24.
        b24_admin_id (str): ID администратора Bitrix24.
        b24_domain (str): Домен Bitrix24.
        s2t_api_key (str): API для Speech2Text.
        donkit_api_key (str): API для Fireworks.
        donkit_bearer_token (str): Bearer-токен для Donkit.
        author (User): Автор организации.
        created_at (datetime): Дата создания.
        updated_at (datetime): Дата последнего изменения.
    """
    name = models.CharField(max_length=255, unique=True, verbose_name="Наименование")
    short_description = models.TextField(blank=True, verbose_name="Краткое описание")

    # Данные amoCRM
    account_amocrm = models.CharField(max_length=255, unique=True, verbose_name="Аккаунт amoCRM")
    bearer_amocrm = models.TextField(verbose_name="Bearer amoCRM")
    send_comments_to_amocrm = models.BooleanField(default=False, verbose_name="Комменты в amoCRM")
    custom_crm = models.BooleanField(
        default=False,
        verbose_name="Организация использует стороннюю CRM"
    )
    
    # Данные Bitrix24
    b24_api_stat = models.TextField(blank=True, null=True, verbose_name="API статистики Bitrix24")
    b24_api_comment = models.TextField(blank=True, null=True, verbose_name="API комментариев Bitrix24")
    b24_api_leads = models.TextField(blank=True, null=True, verbose_name="API лидов Bitrix24") 
    b24_api_lead_status = models.TextField(blank=True, null=True, verbose_name="API статуса лида Bitrix24") 
    b24_admin_id = models.CharField(max_length=255, blank=True, null=True, verbose_name="ID администратора Bitrix24")
    b24_domain = models.CharField(max_length=255, blank=True, null=True, verbose_name="Домен Bitrix24")

    # API-ключи
    s2t_api_key = models.TextField(blank=True, null=True, verbose_name="API Speech2Text")  # Новое поле
    donkit_api_key = models.TextField(blank=True, null=True, verbose_name="API Fireworks")
    donkit_bearer_token = models.TextField(blank=True, null=True, verbose_name="Bearer-токен Donkit")

    total_audio_duration = models.IntegerField(default=0)  # В секундах
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Автор")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата последнего изменения")
    minimal_call_length = models.IntegerField(
        default=30,
        verbose_name="Минимальная длительность звонка (сек)"
    )  
    stats_type = models.IntegerField(
            choices=[(1, "Старая статистика"), (2, "Новая статистика")], 
            default=2, 
            verbose_name="Тип статистики"
        )
        
    max_criteria_score = models.IntegerField(
        default=10,
        verbose_name="Максимальная сумма оценок всех критериев"
    )  

    trial_expires_at = models.DateField(null=True, blank=True, verbose_name="Дата окончания триала")

    show_dealstage_block = models.BooleanField(
        default=False,
        verbose_name="Показывать блок этапов сделок и возражений"
    )

    COMMENT_TYPE_CHOICES = [
        (1, "Только аналитика"),
        (2, "Только саммари"),
        (3, "Аналитика и саммари"),
    ]
    
    comment_type = models.IntegerField(
        choices=COMMENT_TYPE_CHOICES,
        default=3,
        verbose_name="Тип отправляемого комментария"
    )
    summary_to_lead = models.BooleanField(
        default=False,
        verbose_name="Отправлять саммари в сделки"
    )
  
    class Meta:
        verbose_name = "Организация"
        verbose_name_plural = "Организации"
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class IncomingRequest(models.Model):
    """
    Входящий запрос, полученный CRM-система (amoCRM и Bitrix24), содержащий данные о звонке и примечаниях.
    
    Атрибуты:
        source (str): Источник запроса (amoCRM или Bitrix24).
        raw_data (dict): Исходные данные запроса.
        domain (str): Домен amoCRM (если источник amoCRM).
        user_id (str): ID контакта в amoCRM.
        note_id (str): ID примечания в amoCRM.
        domain_b24 (str): Домен Bitrix24 (если источник Bitrix24).
        user_id_b24 (str): ID контакта в Bitrix24.
        call_id_b24 (str): ID звонка в Bitrix24.
        audio_link (str): Ссылка на аудиозапись.
        organization (Organization): Организация, связанная с запросом.
        created_at (datetime): Дата поступления запроса.
    """   
    SOURCE_CHOICES = [
        ("amoCRM", "amoCRM"),
        ("Bitrix24", "Bitrix24"),
    ]

    CALL_DIRECTION_CHOICES = [
        ('incoming', 'Входящий'),
        ('outgoing', 'Исходящий'),
    ]

    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, verbose_name="Источник запроса")
    raw_data = models.JSONField(verbose_name="Тело запроса")  # Хранение полного JSON

    # amoCRM
    domain = models.CharField(max_length=255, blank=True, null=True, verbose_name="Домен amoCRM")
    user_id = models.CharField(max_length=255, blank=True, null=True, verbose_name="ID пользователя amoCRM")
    
    # Bitrix24
    domain_b24 = models.CharField(max_length=255, blank=True, null=True, verbose_name="Домен Bitrix24")
    user_id_b24 = models.CharField(max_length=255, blank=True, null=True, verbose_name="ID контакта Bitrix24")
    call_id_b24 = models.CharField(max_length=255, blank=True, verbose_name="CALL_ID Bitrix24") 
    crm_entity_type = models.CharField(max_length=50, blank=True, null=True, verbose_name="Тип CRM-сущности")
    crm_entity_id = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID CRM-сущности")

    note_id = models.CharField(max_length=255, blank=True, null=True, verbose_name="ID примечания")
    audio_link = models.CharField(max_length=1000, null=True, blank=True, verbose_name="Ссылка на аудиозапись")
    audio_duration = models.IntegerField(null=True, blank=True, default=0, verbose_name="Длительность аудио (сек)")
    
    client_phone = models.CharField(max_length=30, blank=True, null=True, verbose_name="Телефон клиента")
    call_direction = models.CharField(
        max_length=10,
        choices=CALL_DIRECTION_CHOICES,
        default='outgoing',
        verbose_name='Направление звонка'
    )

    deal_stages = models.ManyToManyField(
        "DealStage",
        blank=True,
        related_name="incoming_requests",
        verbose_name="Этапы сделок"
    )

    manager = models.ForeignKey(
        "Manager",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incoming_requests",
        verbose_name="Менеджер"
    )


    organization = models.ForeignKey(
        'Organization', 
        on_delete=models.CASCADE, 
        null=True, blank=True, 
        related_name="requests", 
        verbose_name="Организация"
    )

    ignored = models.BooleanField(default=False, verbose_name="Игнорирован")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата поступления запроса")

    class Meta:
        verbose_name = "Входящий запрос"
        verbose_name_plural = "Входящие запросы"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.crm_entity_type:
            self.crm_entity_type = self.crm_entity_type.lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Request from {self.domain}"


class S2TRequest(models.Model):
    """
    Запрос в сервис Speech2Text для транскрибации аудиозаписи.
    
    Атрибуты:
        organization (Organization): Организация, связанная с запросом.
        incoming_request (IncomingRequest): Входящий запрос, связанный с транскрибацией.
        task_id (str): ID задачи в Speech2Text.
        audio_link (str): Ссылка на аудиофайл.
        raw_result_link (str): Ссылка на raw результат.
        txt_result_link (str): Ссылка на текстовый результат.
        json_result_link (str): Ссылка на JSON результат.
        transcribed_text (str): Транскрибированный текст.
        status (str): Текущий статус задачи.
        created_at (datetime): Дата создания.
        updated_at (datetime): Дата последнего обновления.
    """
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="s2t_requests", verbose_name="Организация")
    incoming_request = models.ForeignKey(
        IncomingRequest, 
        on_delete=models.CASCADE, 
        related_name='related_s2t_requests',  # Убедимся, что это значение совпадает с использованием в шаблоне
        verbose_name="Связанный входящий запрос"
    )
    task_id = models.CharField(max_length=255, verbose_name="ID задачи в Speech2Text")
    audio_link = models.CharField(max_length=1000, verbose_name="Ссылка на аудиофайл")
    raw_result_link = models.CharField(max_length=1000, blank=True, null=True, verbose_name="Ссылка на raw результат")
    txt_result_link = models.CharField(max_length=1000, blank=True, null=True, verbose_name="Ссылка на txt результат")
    json_result_link = models.CharField(max_length=1000, blank=True, null=True, verbose_name="Ссылка на json результат")
    transcribed_text = models.TextField(blank=True, null=True, verbose_name="Транскрибированный текст")
    status = models.CharField(max_length=255, default="pending", verbose_name="Статус задачи")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата последнего обновления")
    
    class Meta:
        verbose_name = "Запрос Speech2Text"
        verbose_name_plural = "Запросы Speech2Text"
        ordering = ['-created_at']

    def __str__(self):
        return f"S2TRequest {self.task_id} для {self.organization.name}"


class Prompt(models.Model):
    """
    Промпт, используемый для генерации вопросов в DeepSeekV3.
    
    Атрибуты:
        name (str): Название промпта.
        description (str): Описание промпта.
        organization (Organization): Организация, связанная с промптом.
        created_at (datetime): Дата создания.
        updated_at (datetime): Дата последнего обновления.
    """
    name = models.CharField(max_length=255, verbose_name="Название промпта")
    description = models.TextField(blank=True, verbose_name="Описание промпта")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="prompts", verbose_name="Организация")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Промпт"
        verbose_name_plural = "Промпты"
        ordering = ['-created_at']

    def __str__(self):
        return self.name
    

class DonkitRequest(models.Model):
    """
    Запрос в DeepSeekV3 для анализа данных.
    
    Атрибуты:
        incoming_request (IncomingRequest): Связанный входящий запрос.
        organization (Organization): Организация, связанная с запросом.
        chat_id (str): ID чата в DeepSeekV3.
        question (str): Заданный вопрос.
        answer (str): Полученный ответ.
        tokens_used (int): Количество использованных токенов на обработку запроса.
        status (str): Статус запроса.
        created_at (datetime): Дата создания.
        updated_at (datetime): Дата последнего обновления.
    """
    incoming_request = models.ForeignKey(
        IncomingRequest, 
        on_delete=models.CASCADE, 
        related_name="related_donkit_requests", 
        verbose_name="Связанный входящий запрос"
    )
    organization = models.ForeignKey(
        Organization, 
        on_delete=models.CASCADE,  
        verbose_name="Организация"
    )
    chat_id = models.CharField(max_length=255, verbose_name="ID чата DeepSeekV3")
    raw_data = models.TextField(blank=True, null=True, verbose_name="Полный ответ нейросети")
    question = models.TextField(verbose_name="Вопрос")
    answer = models.TextField(blank=True, null=True, verbose_name="Ответ")
    tokens_used = models.IntegerField(null=True, blank=True, default=0, verbose_name="Токены")
    status = models.CharField(max_length=255, default="pending", verbose_name="Статус")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    prompt = models.ForeignKey(
        Prompt,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="related_donkit_requests",  # Связь с моделью Prompt
        verbose_name="Используемый промпт"
    )

    class Meta:
        verbose_name = "Запрос DeepSeekV3"
        verbose_name_plural = "Запросы DeepSeekV3"
        ordering = ["-created_at"]

    def __str__(self):
        return f"DeepSeekV3Request {self.chat_id} для {self.organization.name}"


# depricated model
class Criteria(models.Model):
    """
    Таблица для хранения критериев, относящихся к звонку.
    """
    incoming_request = models.OneToOneField(
        IncomingRequest,
        on_delete=models.CASCADE,
        related_name="criteria",
        verbose_name="Входящий запрос"
    )
    meeting = models.BooleanField(default=False, verbose_name="Встреча")
    questions = models.BooleanField(default=False, verbose_name="Вопросы")
    positive = models.BooleanField(default=False, verbose_name="Добро")
    score = models.IntegerField(null=True, blank=True, default=0, verbose_name="Оценка")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Критерий"
        verbose_name_plural = "Критерии"
        ordering = ['-created_at']

    def __str__(self):
        return f"Критерии для запроса {self.incoming_request.id}"


class Objection(models.Model):
    """
    Таблица для хранения типов возражений, которые уникальны для каждой организации.
    """
    name = models.CharField(max_length=255, verbose_name="Название возражения")
    description = models.TextField(blank=True, verbose_name="Описание")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="objections", verbose_name="Организация")
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Автор")
    deleted = models.BooleanField(default=False, verbose_name="Удалено")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    class Meta:
        verbose_name = "Тип возражения"
        verbose_name_plural = "Типы возражений"
        ordering = ['-created_at']

    def __str__(self):
        return self.name
    

class CriteriaSteps(models.Model):
    """
    Модель для хранения новой схемы критериев оценки звонков.
    """
    incoming_request = models.OneToOneField(
        'IncomingRequest',
        on_delete=models.CASCADE,
        related_name="criteria_steps"
    )
        
    criteria_1 = models.IntegerField(null=True, blank=True)
    criteria_2 = models.IntegerField(null=True, blank=True)
    criteria_3 = models.IntegerField(null=True, blank=True)
    criteria_4 = models.IntegerField(null=True, blank=True)
    criteria_5 = models.IntegerField(null=True, blank=True)
    criteria_6 = models.IntegerField(null=True, blank=True)
    criteria_7 = models.IntegerField(null=True, blank=True)

    overall_score = models.IntegerField(null=True, blank=True)  # Общая оценка
    
    contact = models.IntegerField(null=True, blank=True)  # Установление контакта
    needs_analysis = models.IntegerField(null=True, blank=True)  # Выявление потребностей
    presentation = models.IntegerField(null=True, blank=True)  # Презентация
    persuasion = models.IntegerField(null=True, blank=True)  # Убеждение
    follow_up = models.IntegerField(null=True, blank=True)  # Следующие шаги
    #objections = models.IntegerField(null=True, blank=True)  # Возражения
    objection = models.ForeignKey(
        "Objection",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="criteria_steps",
        verbose_name="Тип возражения"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Критерий 2.0"
        verbose_name_plural = "Критерии 2.0"
        ordering = ['-created_at']

    def __str__(self):
        return f"Критерии 2.0 для звонка #{self.incoming_request.id} (Оценка: {self.overall_score})"



class CriteriaLabel(models.Model):
    organization = models.ForeignKey(
        'Organization', 
        on_delete=models.CASCADE,
        related_name="criteria_labels",
        null=False,
        blank=False
    )
    position = models.PositiveSmallIntegerField()  # 1...7
    label = models.CharField(max_length=255)       # Название из аналитики

    class Meta:
        unique_together = ('organization', 'position')
        ordering = ['organization', 'position']
        verbose_name = "Наименование критерия"
        verbose_name_plural = "Наименование критериев"

    def __str__(self):
        return f"{self.organization}: {self.position}. {self.label}"
    
    
class DealStage(models.Model):
    """
    Таблица для хранения сделок.
    """
    CRM_TYPE_CHOICES = [
        ("amoCRM", "amoCRM"),
        ("Bitrix24", "Bitrix24"),
    ]

    DEAL_TYPE_CHOICES = [
        ("first", "Первый контакт"),
        ("second", "Повторное касание"),
        ("final", "Закрытие сделки"),
    ]

    organization = models.ForeignKey(
        Organization, 
        on_delete=models.CASCADE, 
        related_name="deal_stages", 
        verbose_name="Организация"
    )
    crm_type = models.CharField(max_length=20, choices=CRM_TYPE_CHOICES, verbose_name="Тип CRM")
    deal_id_crm = models.CharField(max_length=255, verbose_name="ID сделки в CRM")
    deal_type = models.CharField(max_length=20, choices=DEAL_TYPE_CHOICES, verbose_name="Тип сделки")
    status = models.CharField(max_length=255, blank=True, null=True, verbose_name="Статус сделки")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Сделка"
        verbose_name_plural = "Сделки"
        ordering = ['-created_at']

    def __str__(self):
        return f"Сделка {self.deal_id_crm} ({self.deal_type}) в {self.organization.name}"


class Department(models.Model):
    """
    Таблица для хранения отделов в орагнизациях.
    """ 
    name = models.CharField(max_length=255, verbose_name="Название отдела")
    description = models.TextField(blank=True, verbose_name="Описание")
    organization = models.ForeignKey(
        Organization, 
        on_delete=models.CASCADE, 
        related_name="departments", 
        verbose_name="Организация"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Отдел"
        verbose_name_plural = "Отделы"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
    

class Manager(models.Model):
    """
    Таблица для хранения данных о менеджерах.
    """
    organization = models.ForeignKey(
        Organization, 
        on_delete=models.CASCADE, 
        related_name="managers", 
        verbose_name="Организация"
    )
    department = models.ForeignKey(
        "Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managers",
        verbose_name="Отдел"
    )
    manager_id_crm = models.CharField(max_length=255, verbose_name="ID менеджера в CRM")
    full_name = models.CharField(max_length=255, verbose_name="ФИО менеджера")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Менеджер"
        verbose_name_plural = "Менеджеры"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.full_name} (ID {self.manager_id_crm}) в {self.organization.name}"
    

class File(models.Model):
    """
    Модель для хранения информации о загруженных файлах.
    """
    id = models.AutoField(primary_key=True)
    filename = models.CharField(max_length=255, verbose_name="Имя файла")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Пользователь")
    organization = models.ForeignKey("Organization", on_delete=models.CASCADE, related_name="files", verbose_name="Организация")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата добавления")

    class Meta:
        verbose_name = "Файл"
        verbose_name_plural = "Файлы"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.filename} (Организация: {self.organization.name})"
    


class WeeklyReport(models.Model):
    organization = models.ForeignKey("Organization", on_delete=models.CASCADE, related_name="weekly_reports")
    week_start = models.DateField()
    week_end = models.DateField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


    class Meta:
        unique_together = ('organization', 'week_start')

    def __str__(self):
        return f"{self.organization.name} | {self.week_start} – {self.week_end} ({'Активный' if self.is_active else 'Архив'})"

    @property
    def active_insights(self):
        """
        Возвращает QuerySet инсайтов для этого отчёта (активного еженедельного отчёта).
        """
        return self.insights.all()


class WeeklyInsight(models.Model):
    report = models.ForeignKey(WeeklyReport, on_delete=models.CASCADE, related_name="insights")
    title = models.CharField(max_length=255)
    request_ids = models.JSONField(default=list)  # список ID обработанных IncomingRequest
    frequency = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('report', 'title')

    def __str__(self):
        return f"{self.title} ({len(self.request_ids)} случаев)"

    @property
    def examples_all(self):
        """
        Возвращает все примеры для данного инсайта.
        """
        return self.examples.all()
    
    
class InsightExample(models.Model):
    insight = models.ForeignKey(WeeklyInsight, on_delete=models.CASCADE, related_name="examples")
    text = models.TextField()
    incoming_requests = models.ManyToManyField(IncomingRequest, related_name="insight_examples")

    def __str__(self):
        return f"Пример для '{self.insight.title}'"
    

class WeeklyFactorReport(models.Model):
    organization = models.ForeignKey("Organization", on_delete=models.CASCADE, related_name="weekly_factor_reports")
    week_start = models.DateField()
    week_end = models.DateField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('organization', 'week_start')

    def __str__(self):
        return f"{self.organization.name} | {self.week_start} – {self.week_end} (Factors)"

    @property
    def active_factors(self):
        return self.factors.all()


class WeeklyFactor(models.Model):
    report = models.ForeignKey(WeeklyFactorReport, on_delete=models.CASCADE, related_name="factors")
    title = models.CharField(max_length=255)
    request_ids = models.JSONField(default=list)
    frequency = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('report', 'title')

    def __str__(self):
        return f"{self.title} ({len(self.request_ids)} случаев)"


class FactorExample(models.Model):
    factor = models.ForeignKey(WeeklyFactor, on_delete=models.CASCADE, related_name="examples")
    text = models.TextField()
    incoming_requests = models.ManyToManyField(IncomingRequest, related_name="factor_examples")

    def __str__(self):
        return f"Пример для '{self.factor.title}'"




class WeeklyErrorReport(models.Model):
    organization = models.ForeignKey("Organization", on_delete=models.CASCADE, related_name="weekly_error_reports")
    week_start = models.DateField()
    week_end = models.DateField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('organization', 'week_start')

    def __str__(self):
        return f"{self.organization.name} | {self.week_start} – {self.week_end} (Errors)"

    @property
    def active_errors(self):
        return self.errors.all()


class WeeklyError(models.Model):
    report = models.ForeignKey(WeeklyErrorReport, on_delete=models.CASCADE, related_name="errors")
    title = models.CharField(max_length=255)
    request_ids = models.JSONField(default=list)
    frequency = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('report', 'title')

    def __str__(self):
        return f"{self.title} ({len(self.request_ids)} случаев)"


class ErrorExample(models.Model):
    error = models.ForeignKey(WeeklyError, on_delete=models.CASCADE, related_name="examples")
    text = models.TextField()
    incoming_requests = models.ManyToManyField(IncomingRequest, related_name="error_examples")

    def __str__(self):
        return f"Пример для '{self.error.title}'"