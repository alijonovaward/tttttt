from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from .views import *
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('organization/<int:pk>/', views.organization_detail, name='organization_detail'),
    path('add_prompt/', views.add_prompt, name='add_prompt'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.custom_logout_view, name='logout'),
    path('get_call/', GetCallWebhook.as_view(), name='get_call'),  # С завершающим слэшем
    path('get_call', GetCallWebhook.as_view(), name='get_call_no_slash'),  # Без завершающего слэша
    path('get_call_b24/', GetCallBitrixWebhook.as_view(), name='get_call_b24'),
    path('get_call_b24', GetCallBitrixWebhook.as_view(), name='get_call_b24_no_slash'),
    # Другие маршруты
    path('send_to_transcription/<int:request_id>/', views.send_to_transcription, name='send_to_transcription'),
    path('send_to_donkit/<int:incoming_request_id>/', views.send_to_donkit, name='send_to_donkit'),
    path('add_crm_note/<int:incoming_request_id>/', add_crm_note_view, name='add_crm_note'),
    path('export-requests/', views.export_requests_csv, name='export_requests_csv'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
