from pathlib import Path
import os
from celery.schedules import crontab

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-2KJ^6fl345uaavwu)_#28r8m+zd_bh7nw@ad-@lad^^d$^0&bh#d'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = ['45.139.78.209', 'plus-script.ru', 'www.plus-script.ru', 'localhost', '127.0.0.1']


# Application definition

INSTALLED_APPS = [
    'zapp',
    'django_celery_beat',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'ave_config2.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]


WSGI_APPLICATION = 'ave_config2.wsgi.application'


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'script_database',
        'USER': 'aventica_user',
        'PASSWORD': 'Ak2xmDMScm6xjK8c',
        'HOST': 'localhost',  # Или IP, если база на другом сервере
        'PORT': '5432',
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Europe/Moscow'

USE_I18N = True

USE_TZ = True

# Путь для хранения статических файлов
STATIC_URL = '/static/'

# Абсолютный путь к директории, где будут собираться статические файлы
STATIC_ROOT = BASE_DIR / 'static'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'  # URL для перенаправления на вход
LOGIN_REDIRECT_URL = '/'  # URL после успешной авторизации
LOGOUT_REDIRECT_URL = '/login/'  # URL после выхода


# Брокер для Celery (Redis)
CELERY_BROKER_URL = 'redis://localhost:6379/0'  # Или ваш фактический URL брокера
CELERY_RESULT_BACKEND = 'redis://localhost:6379/1'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_EXPIRES = 3600
CELERY_TIMEZONE = 'Europe/Moscow'
CELERY_ENABLE_UTC = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_ACKS_ON_FAILURE_OR_TIMEOUT = True
CELERY_TASK_SOFT_TIME_LIMIT = 150     # мягкий таймаут (уберёт залипшие HTTP)

DEFAULT_ORGANIZATION_PROMPT = """
Ты тренер по продажам. Оцени диалог от 1 до 5 по следующим критериям. 

1. установление контакта: использовал приветствие и программирование по структуре встречи, взял инициативу разговора. 
2. выявление потребностей: задавал открытые вопросы, пытался выяснить, что важно для клиента и критерии выбора. 
3 презентация решения: резюмировал потребности, рассказал о предложении. 
4 работа с возражениями: слушает, не спорит уточняет конкретику, соглашается, где это уместно, приводит аргументы, запрашивает обратную связь. 
5. Своевременно переходит к следующим шагам для начала сотрудничества, подводит итоги разговора и позитивно завершает диалог. 

В конце сделай общую оценку диалога и аргументируй с примерами. 
Отдельно напиши если были возражения, они могут быть 4 видов: 
1 – цена, 
2 - не интересно, 
3 – уже работают с конкурентом, 
0 – нет возражений или тип возражения не определен. 

Твой ответ должен быть написан строго по шаблону: 
1. Установление контакта. (оценка: цифра от 1 до 5) 
2. Выявление потребностей. (оценка: цифра от 1 до 5) 
3. Презентация. (оценка: цифра от 1 до 5) 
4. Работа с возражениями. (оценка: цифра от 1 до 5) 
5. Следующие шаги. (оценка: цифра от 1 до 5) 
6. Общая оценка. (оценка: цифра от 1 до 5) 
7. Возражения. (тут указывается только цифра, соответствующая типу возражения) 
8. Обратная связь: (тут перечисляются примеры диалогов и рекомендации по их улучшению)

"""
