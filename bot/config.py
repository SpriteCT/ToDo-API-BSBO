import os

from dotenv import load_dotenv

load_dotenv()


TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Базовый URL вашего backend API (FastAPI)
# Если API_BASE_URL не задан явно, используем BACKEND_PORT для построения URL
_backend_port = os.getenv("BACKEND_PORT", "8000")
_api_base_url = os.getenv("API_BASE_URL")
if _api_base_url:
    API_BASE_URL: str = _api_base_url
else:
    # По умолчанию используем localhost для локального запуска или backend для Docker
    _backend_host = os.getenv("BACKEND_HOST", "localhost")
    API_BASE_URL: str = f"http://{_backend_host}:{_backend_port}/api/v3"


if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError(
        "Не задан TELEGRAM_BOT_TOKEN в .env. "
        "Добавьте TELEGRAM_BOT_TOKEN=<ваш_токен_бота> в .env файл."
    )


