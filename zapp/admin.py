from django.contrib import admin
from django import forms
from .models import *
from django.utils.html import format_html

@admin.register(Criteria)
class CriteriaAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_incoming_request_link', 'meeting', 'questions', 'positive', 'score', 'created_at', 'updated_at')
    search_fields = ('incoming_request__note_id', 'incoming_request__organization__name')
    list_filter = ('meeting', 'questions', 'positive', 'score', 'created_at')
    readonly_fields = ('created_at', 'updated_at')

    def get_incoming_request_link(self, obj):
        if obj.incoming_request:
            return format_html('<a href="{}" target="_blank">{}</a>',
                               f"/admin/zapp/incomingrequest/{obj.incoming_request.id}/",
                               obj.incoming_request.id)
        return "-"
    
    get_incoming_request_link.short_description = "ID входящего запроса"


class CriteriaLabelInline(admin.TabularInline):
    model = CriteriaLabel
    extra = 7
    max_num = 7
    fields = ('position', 'label')
    ordering = ('position',)


@admin.register(CriteriaLabel)
class CriteriaLabelAdmin(admin.ModelAdmin):
    list_display = ('organization', 'position', 'label')
    list_filter = ('organization', 'position')
    search_fields = ('label', 'organization__name')
    ordering = ('organization', 'position')


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'name', 'account_amocrm', 'send_comments_to_amocrm', 'b24_domain', 's2t_api_key',
        'donkit_api_key', 'max_criteria_score', 'custom_crm', 'total_audio_duration', 'show_dealstage_block', 'comment_type', 'summary_to_lead', 'author', 'created_at', 'updated_at'
    )
    list_editable = ("show_dealstage_block",)
    inlines = [CriteriaLabelInline]
    search_fields = ('name', 'account_amocrm', 'b24_domain')
    list_filter = ('created_at', 'custom_crm')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'organization', 'description')
    search_fields = ('name', 'organization__name', 'department__name')
    list_filter = ('organization',)
    ordering = ['organization', 'name']


@admin.register(Manager)
class ManagerAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'manager_id_crm', 'full_name', 'department')
    search_fields = ('full_name', 'manager_id_crm', 'organization__name', 'department__name')
    list_filter = ('organization', 'department')
    ordering = ['organization', 'full_name']


@admin.register(DealStage)
class DealStageAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'status', 'crm_type', 'deal_id_crm', 'deal_type')
    search_fields = ('deal_id_crm', 'organization__name')
    list_filter = ('crm_type', 'status', 'deal_type', 'organization')
    ordering = ['organization', '-id']


class S2TRequestInline(admin.TabularInline):
    model = S2TRequest
    extra = 0
    readonly_fields = ('created_at', 'updated_at')


class DonkitRequestInline(admin.TabularInline):
    model = DonkitRequest
    extra = 0
    readonly_fields = ('created_at', 'updated_at')


@admin.register(S2TRequest)
class S2TRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'get_incoming_request', 'task_id', 'status', 'created_at', 'updated_at')
    search_fields = ('task_id', 'organization__name', 'incoming_request__note_id')
    list_filter = ('status', 'created_at')
    readonly_fields = ('created_at', 'updated_at')

    def get_incoming_request(self, obj):
        return obj.incoming_request.id if obj.incoming_request else "-"
    get_incoming_request.short_description = "ID запроса"


@admin.register(IncomingRequest)
class IncomingRequestAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'note_id', 'source', 'call_direction', 'ignored', 'manager', 'call_direction', 'get_deal_stages', 'domain', 'domain_b24', 'user_id', 'user_id_b24',
        'organization', 'audio_duration', 'created_at'
    )
    search_fields = ('note_id', 'domain', 'domain_b24', 'organization__name', 'user_id', 'user_id_b24', 'crm_entity_id', 'crm_entity_type')
    list_filter = ('created_at', 'organization', 'source', 'ignored')
    readonly_fields = ('raw_data', 'created_at')
    inlines = [S2TRequestInline, DonkitRequestInline]

    def get_deal_stages(self, obj):
        """Возвращает список ID сделок, связанных с запросом"""
        return ", ".join([str(deal.deal_id_crm) for deal in obj.deal_stages.all()])

    get_deal_stages.short_description = "ID сделок"


@admin.register(DonkitRequest)
class DonkitRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'prompt', 'tokens_used', 'created_at', 'updated_at', 'status', 'get_incoming_request')
    search_fields = ('incoming_request__note_id', 'organization__name')
    list_filter = ('status', 'created_at', 'updated_at', 'prompt')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')

    def get_incoming_request(self, obj):
        return obj.incoming_request.id if obj.incoming_request else "-"
    get_incoming_request.short_description = "ID запроса"


@admin.register(Prompt)
class PromptAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'short_description', 'organization', 'created_at')
    list_filter = ('organization', 'created_at')
    search_fields = ('name', 'organization__name')

    @admin.display(description="Описание")
    def short_description(self, obj):
        return (obj.description[:75] + '...') if len(obj.description) > 75 else obj.description


@admin.register(CriteriaSteps)
class CriteriaStepsAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'get_incoming_request_link', 'get_organization_name',
        'criteria_1', 'criteria_2', 'criteria_3',
        'criteria_4', 'criteria_5', 'criteria_6', 'criteria_7',
        'overall_score', 'created_at', 'updated_at'
    )
    search_fields = (
        'incoming_request__id',
        'incoming_request__organization__name',
    )
    list_filter = (
        'criteria_1', 'criteria_2', 'criteria_3',
        'criteria_4', 'criteria_5', 'criteria_6', 'criteria_7',
        'overall_score', 'created_at'
    )
    readonly_fields = ('created_at', 'updated_at')

    def get_incoming_request_link(self, obj):
        if obj.incoming_request:
            return format_html(
                '<a href="{}" target="_blank">{}</a>',
                f"/admin/zapp/incomingrequest/{obj.incoming_request.id}/",
                obj.incoming_request.id
            )
        return "-"
    get_incoming_request_link.short_description = "ID входящего запроса"

    def get_organization_name(self, obj):
        if obj.incoming_request and obj.incoming_request.organization:
            return obj.incoming_request.organization.name
        return "-"
    get_organization_name.short_description = "Организация"
    get_organization_name.admin_order_field = 'incoming_request__organization__name'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "objection":
            object_id = request.resolver_match.kwargs.get("object_id")
            if object_id:
                try:
                    criteria_step = CriteriaSteps.objects.select_related("incoming_request__organization").get(id=object_id)
                    organization = criteria_step.incoming_request.organization
                    kwargs["queryset"] = Objection.objects.filter(deleted=False, organization=organization)
                except CriteriaSteps.DoesNotExist:
                    pass
            else:
                kwargs["queryset"] = Objection.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Objection)
class ObjectionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description', 'organization', 'author', 'deleted', 'created_at', 'updated_at')
    search_fields = ('name', 'description', 'organization__name')
    list_filter = ('deleted', 'organization', 'created_at')
    readonly_fields = ('created_at', 'updated_at')


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get("role")
        organization = cleaned_data.get("organization")

        if role in ["admin", "user"] and not organization:
            raise forms.ValidationError("Для ролей 'Администратор' и 'Пользователь' необходимо выбрать организацию.")
        return cleaned_data

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    form = UserProfileForm
    list_display = ('user', 'role', 'organization')
    list_filter = ('role', 'organization')
    search_fields = ('user__username', 'organization__name')

  
@admin.register(WeeklyReport)
class WeeklyReportAdmin(admin.ModelAdmin):
    list_display = ('organization', 'week_start', 'week_end', 'is_active', 'created_at')
    list_filter = ('organization', 'is_active')
    search_fields = ('organization__name',)


@admin.register(WeeklyInsight)
class WeeklyInsightAdmin(admin.ModelAdmin):
    list_display = ('title', 'frequency', 'report', 'created_at')
    search_fields = ('title', 'report__organization__name')
    list_filter = ('report__organization',)


@admin.register(InsightExample)
class InsightExampleAdmin(admin.ModelAdmin):
    list_display = ('id', 'insight', "get_request_ids", 'text')
    search_fields = ('text', 'insight__title', 'insight__report__organization__name')
    list_filter = ('insight__report__organization',)
    readonly_fields = ("get_request_ids",)

    def get_request_ids(self, obj):
        return ", ".join(str(req.id) for req in obj.incoming_requests.all())

    get_request_ids.short_description = "Привязанные звонки (ID)"


@admin.register(WeeklyErrorReport)
class WeeklyErrorReportAdmin(admin.ModelAdmin):
    list_display = ('organization', 'week_start', 'week_end', 'is_active', 'created_at')
    list_filter = ('organization', 'is_active')
    search_fields = ('organization__name',)

@admin.register(WeeklyError)
class WeeklyErrorAdmin(admin.ModelAdmin):
    list_display = ('title', 'report', 'frequency', 'created_at')
    list_filter = ('report',)
    search_fields = ('title',)

@admin.register(ErrorExample)
class ErrorExampleAdmin(admin.ModelAdmin):
    list_display = ('error', 'text')
    search_fields = ('text', 'error__title')

@admin.register(WeeklyFactorReport)
class WeeklyFactorReportAdmin(admin.ModelAdmin):
    list_display = ('organization', 'week_start', 'week_end', 'is_active', 'created_at')
    list_filter = ('organization', 'is_active')
    search_fields = ('organization__name',)

@admin.register(WeeklyFactor)
class WeeklyFactorAdmin(admin.ModelAdmin):
    list_display = ('title', 'report', 'frequency', 'created_at')
    list_filter = ('report',)
    search_fields = ('title',)

@admin.register(FactorExample)
class FactorExampleAdmin(admin.ModelAdmin):
    list_display = ('factor', 'text')
    search_fields = ('text', 'factor__title')



# Безопасно регистрируем, если еще не зарегистрировано
if InsightExample not in admin.site._registry:
    admin.site.register(InsightExample, InsightExampleAdmin)