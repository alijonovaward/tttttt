## DEPRECATED

from zapp.models import IncomingRequest, DealStage

# Проходим по всем входящим запросам, у которых есть старая связь
for request in IncomingRequest.objects.all():
    if request.deal_stage:  # Если у запроса есть привязанная сделка
        request.temp_deal_stages.add(request.deal_stage)  # Копируем связь в новое поле

print("Данные успешно перенесены!")


    # deal_stage = models.ForeignKey(
    #     "DealStage",
    #     on_delete=models.SET_NULL,
    #     null=True,
    #     blank=True,
    #     related_name="incoming_requests",
    #     verbose_name="Этап сделки"
    # )