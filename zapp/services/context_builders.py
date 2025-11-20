from collections import namedtuple
from datetime import datetime, timedelta
from django.db.models import Avg, Count, Q
from ..models import *
import logging

logger = logging.getLogger(__name__)

def build_stats_context(request, organization, organizations_queryset):
    
    audio_min = request.GET.get("audio_min")
    audio_max = request.GET.get("audio_max")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    manager_id = request.GET.get("manager_id")
    department_id = request.GET.get("department_id")
    overall_score_range = request.GET.get("overall_score_range")
    include_ignored = request.GET.get("include_ignored") == "1"

    if manager_id:
        department_id = None

    if date_from and not date_to:
        date_to = datetime.today().date().isoformat()
    elif date_to and not date_from:
        date_from = datetime.today().date().isoformat()

    # === Выборка с учетом критериев
    criteria_filters_active = any(
        request.GET.get(f"crit{i}_min") or request.GET.get(f"crit{i}_max") for i in range(1, 8)
    ) or overall_score_range

    if criteria_filters_active:
        criteria_qs = CriteriaSteps.objects.filter(incoming_request__organization=organization)
        
        if not include_ignored:
            criteria_qs = criteria_qs.filter(incoming_request__ignored=False)

        if date_from:
            criteria_qs = criteria_qs.filter(incoming_request__created_at__gte=date_from)
        if date_to:
            try:
                date_to_dt = datetime.strptime(date_to, "%Y-%m-%d").date() + timedelta(days=1)
                criteria_qs = criteria_qs.filter(incoming_request__created_at__lt=date_to_dt)
            except Exception:
                pass
        if manager_id:
            criteria_qs = criteria_qs.filter(incoming_request__manager_id=manager_id)
        if department_id:
            criteria_qs = criteria_qs.filter(incoming_request__manager__department_id=department_id)
        if audio_min:
            criteria_qs = criteria_qs.filter(incoming_request__audio_duration__gte=int(audio_min))
        if audio_max:
            criteria_qs = criteria_qs.filter(incoming_request__audio_duration__lte=int(audio_max))

        label_qs = CriteriaLabel.objects.filter(organization=organization).order_by("position")
        criteria_labels = {f"crit{row.position}": row.label for row in label_qs}
        criteria_labels_filtered = list(criteria_labels.keys())

        for field_key in criteria_labels_filtered:
            model_field = field_key.replace("crit", "criteria_")
            min_val = request.GET.get(f"{field_key}_min")
            max_val = request.GET.get(f"{field_key}_max")
            if min_val:
                try:
                    criteria_qs = criteria_qs.filter(**{f"{model_field}__gte": float(min_val)})
                except ValueError:
                    pass
            if max_val:
                try:
                    criteria_qs = criteria_qs.filter(**{f"{model_field}__lte": float(max_val)})
                except ValueError:
                    pass

        if overall_score_range:
            max_score = organization.max_criteria_score or 10  # ← может быть 5 или 10
            if max_score:
                if overall_score_range == "lt25":
                    criteria_qs = criteria_qs.filter(overall_score__lt=(0.25 * max_score))
                elif overall_score_range == "25to50":
                    criteria_qs = criteria_qs.filter(overall_score__gte=(0.25 * max_score), overall_score__lt=(0.5 * max_score))
                elif overall_score_range == "50to75":
                    criteria_qs = criteria_qs.filter(overall_score__gte=(0.5 * max_score), overall_score__lt=(0.75 * max_score))
                elif overall_score_range == "gt75":
                    criteria_qs = criteria_qs.filter(overall_score__gte=(0.75 * max_score))

        request_ids = list(criteria_qs.values_list("incoming_request_id", flat=True))
        qs = IncomingRequest.objects.filter(id__in=request_ids)
        
        if not include_ignored:
            qs = qs.filter(ignored=False)
    else:
        qs = IncomingRequest.objects.filter(organization=organization)
        
        if not include_ignored:
            qs = qs.filter(ignored=False)

        if date_from:
            qs = qs.filter(created_at__gte=date_from)
        if date_to:
            try:
                date_to_dt = datetime.strptime(date_to, "%Y-%m-%d").date() + timedelta(days=1)
                qs = qs.filter(created_at__lt=date_to_dt)
            except Exception:
                pass
        if manager_id:
            qs = qs.filter(manager_id=manager_id)
        if department_id:
            qs = qs.filter(manager__department_id=department_id)
        if audio_min:
            qs = qs.filter(audio_duration__gte=int(audio_min))
        if audio_max:
            qs = qs.filter(audio_duration__lte=int(audio_max))

        label_qs = CriteriaLabel.objects.filter(organization=organization).order_by("position")
        criteria_labels = {f"crit{row.position}": row.label for row in label_qs}
        criteria_labels_filtered = list(criteria_labels.keys())

    request_ids = list(qs.values_list("id", flat=True))
    max_duration = qs.aggregate(models.Max("audio_duration"))["audio_duration__max"] or 100
    min_duration = qs.aggregate(models.Min("audio_duration"))["audio_duration__min"] or 0

    total_duration_seconds = qs.aggregate(total=models.Sum("audio_duration"))["total"] or 0
    minutes = total_duration_seconds // 60
    seconds = total_duration_seconds % 60
    formatted_duration = f"{minutes} мин {seconds} с"

    if not request_ids:
        return {
            "organizations": Organization.objects.all(),
            "selected_organization": organization,
            "processed_requests": [],
            "managers": organization.managers.all(),
            "departments": Department.objects.filter(organization=organization),
            "manager_chart_data": {"labels": [], "scores": [], "calls": []},
            "deal_stage_chart": {"labels": [], "values": [], "total": 0},
            "objection_chart_data": {"labels": [], "values": [], "total": 0},
            "criteria_scores": {},
            "criteria_labels": criteria_labels,
            "criteria_labels_filtered": criteria_labels_filtered,
            "criteria_icons": get_criteria_icons(),
            "max_duration": max_duration,
            "min_duration": min_duration,
            "stats_total_calls": 0,
            "stats_incoming_calls": 0,
            "stats_outgoing_calls": 0,
            "stats_total_minutes": formatted_duration,
        }

    return {
        "organizations": organizations_queryset,
        "selected_organization": organization,
        "processed_requests": list(qs),
        "managers": organization.managers.all(),
        "departments": Department.objects.filter(organization=organization),
        "manager_chart_data": get_manager_chart_data(organization, request_ids, manager_id, department_id),
        "deal_stage_chart": get_deal_stage_data(organization, request_ids),
        "objection_chart_data": get_objection_chart_data(organization, request_ids),
        "criteria_scores": get_criteria_scores(organization, request_ids, manager_id, department_id, request=request),
        "criteria_labels": criteria_labels,
        "criteria_labels_filtered": criteria_labels_filtered,
        "criteria_icons": get_criteria_icons(),
        "max_duration": max_duration,
        "min_duration": min_duration,
        "stats_total_minutes": formatted_duration,
        **get_call_stats(organization, request_ids)
    }


def get_call_stats(organization, request_ids=None):
    qs = organization.requests.all()
    if request_ids:
        qs = qs.filter(id__in=request_ids)
    return {
        "stats_total_calls": qs.count(),
        "stats_incoming_calls": qs.filter(call_direction="incoming").count(),
        "stats_outgoing_calls": qs.filter(call_direction="outgoing").count(),
    }


def get_manager_chart_data(organization, request_ids=None, manager_id=None, department_id=None):
    ManagerStat = namedtuple("ManagerStat", ["full_name", "normalized_score", "call_count"])

    qs = Manager.objects.filter(organization=organization)

    if department_id:
        qs = qs.filter(department_id=department_id)

    if manager_id:
        qs = qs.filter(id=manager_id)

    if request_ids:
        qs = qs.annotate(
            call_count=Count("incoming_requests", filter=Q(incoming_requests__id__in=request_ids), distinct=True),
            avg_score=Avg("incoming_requests__criteria_steps__overall_score", filter=Q(incoming_requests__id__in=request_ids)),
        )
    else:
        qs = qs.annotate(
            call_count=Count("incoming_requests", distinct=True),
            avg_score=Avg("incoming_requests__criteria_steps__overall_score"),
        )

    qs = qs.filter(avg_score__isnull=False)
    
    max_score = organization.max_criteria_score or 10  # ← значение из модели Organization

    manager_stats = []
    for m in qs:
        avg = m.avg_score or 0
        normalized = round((avg / max_score) * 100, 2) if max_score else 0
        manager_stats.append(ManagerStat(m.full_name, normalized, m.call_count))

    # Сортируем: сначала по количеству звонков, потом по оценке
    manager_stats.sort(key=lambda m: (-m.call_count, -m.normalized_score))

    return {
        "labels": [m.full_name for m in manager_stats],
        "scores": [m.normalized_score for m in manager_stats],
        "calls": [m.call_count for m in manager_stats],
    }


def get_objection_chart_data(organization, request_ids=None):
    qs = Objection.objects.filter(organization=organization, deleted=False)

    if request_ids:
        qs = qs.annotate(
            count=Count("criteria_steps", filter=Q(criteria_steps__incoming_request__id__in=request_ids))
        )
    else:
        qs = qs.annotate(count=Count("criteria_steps"))

    values = qs.values("name", "count")

    return {
        "labels": [item["name"] for item in values],
        "values": [item["count"] for item in values],
        "total": sum(item["count"] for item in values),
    }


def get_deal_stage_data(organization, request_ids=None):
    deal_type_labels = {
        "first": "Первый контакт",
        "second": "Повторный звонок",
        "final": "Закрытие сделки",
    }

    qs = DealStage.objects.filter(organization=organization)

    if request_ids:
        qs = qs.annotate(
            call_count=Count("incoming_requests", filter=Q(incoming_requests__id__in=request_ids))
        )
    else:
        qs = qs.annotate(call_count=Count("incoming_requests"))

    values = qs.values("deal_type", "call_count")

    mapped = {
        deal_type_labels.get(stage["deal_type"], stage["deal_type"]): stage["call_count"]
        for stage in values
    }

    return {
        "labels": list(mapped.keys()),
        "values": list(mapped.values()),
        "total": sum(mapped.values()),
    }


def get_criteria_scores(organization, request_ids=None, manager_id=None, department_id=None, request=None):
    qs = CriteriaSteps.objects.filter(incoming_request__organization=organization)

    if request_ids is None or request_ids:
        # Фильтруем только по ignored, если request_ids есть или фильтрация активна
        include_ignored = request.GET.get("include_ignored") == "1"
        if not include_ignored:
            qs = qs.filter(incoming_request__ignored=False)

    if request_ids is not None:
        qs = qs.filter(incoming_request_id__in=request_ids)
    if manager_id:
        qs = qs.filter(incoming_request__manager_id=manager_id)
    elif department_id:
        qs = qs.filter(incoming_request__manager__department_id=department_id)

    scores = {}
    for i in range(1, 8):
        field_name = f"criteria_{i}"
        key = f"crit{i}"
        avg = qs.aggregate(avg=Avg(field_name))["avg"]
        if avg is not None:
            scores[key] = round(avg, 2)

    return scores


def get_criteria_icons():
    return {
        "Установление контакта": "user",
        "Выявление потребностей": "search",
        "Презентация": "presentation",
        "Работа с возражениями": "shield",
        "Завершение": "check",
    }