import requests
from pydub import AudioSegment
from io import BytesIO
import logging

logger = logging.getLogger(__name__)

def get_audio_duration(url):
    """
    Вычисляет длину аудиофайла в секундах по URL.
    """
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()  # Проверяем, что файл доступен
        audio = AudioSegment.from_file(BytesIO(response.content))  # Читаем аудио в память
        return round(audio.duration_seconds)  # Длина в секундах
    except Exception as e:
        logger.error(f"Ошибка получения длины аудио: {str(e)}")
        return 0