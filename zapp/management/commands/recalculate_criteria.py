from django.core.management.base import BaseCommand
from zapp.models import DonkitRequest
from zapp.services.t_model import analyze_criteria_20


class Command(BaseCommand):
    help = 'Повторно анализирует и сохраняет критерии из ответов нейросети (DonkitRequest.answer)'

    def handle(self, *args, **kwargs):
        updated_count = 0
        total = 0

        queryset = DonkitRequest.objects.select_related("incoming_request").all()

        for dr in queryset:
            total += 1
            if not dr.answer or not dr.incoming_request:
                continue

            result = analyze_criteria_20(dr.answer, dr.incoming_request)
            if result:
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(f"Готово! Обработано {total} записей, успешно обновлено {updated_count} критериев."))