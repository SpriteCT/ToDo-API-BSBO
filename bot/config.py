import os

from dotenv import load_dotenv

load_dotenv()


TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Базовый URL вашего backend API (FastAPI)
# По умолчанию — локальный запуск сервера
API_BASE_URL: str = os.getenv("API_BASE_URL", "http://localhost:8000/api/v3")


if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError(
        "Не задан TELEGRAM_BOT_TOKEN в .env. "
        "Добавьте TELEGRAM_BOT_TOKEN=<ваш_токен_бота> в .env файл."
    )


