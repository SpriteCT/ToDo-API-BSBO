import os
from dotenv import load_dotenv

load_dotenv()

# Порт для запуска FastAPI сервера
PORT: int = int(os.getenv("PORT", "8000"))

# Хост для запуска сервера
HOST: str = os.getenv("HOST", "0.0.0.0")

