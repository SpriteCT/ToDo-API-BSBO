# ToDo API Backend

Backend API для управления задачами с использованием матрицы Эйзенхауэра.

## 📁 Структура

- `main.py` — точка входа FastAPI приложения
- `database.py` — подключение к PostgreSQL через async SQLAlchemy
- `models/` — SQLAlchemy модели (`User`, `Task`)
- `routers/` — API маршруты:
  - `auth.py` — авторизация, регистрация, смена пароля
  - `tasks.py` — CRUD операции с задачами
  - `stats.py` — статистика по задачам
- `schemas.py`, `schemas_auth.py` — Pydantic схемы для валидации
- `scheduler.py` — планировщик для автоматического обновления срочности задач
- `utils.py` — утилиты для вычисления квадрантов и срочности
- `auth_utils.py` — функции для работы с JWT и паролями
- `dependencies.py` — зависимости FastAPI (аутентификация)

## 🚀 Запуск

### Через Docker Compose (рекомендуется)

Из корня проекта:
```bash
docker-compose up --build backend
```

### Локальный запуск

1. Установите зависимости:
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
# или
source .venv/bin/activate  # Linux/macOS

pip install -r requirements.txt
```

2. Настройте переменные окружения:
```bash
# Windows
set DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/postgres
set SECRET_KEY=your-secret-key-here
set PORT=8000  # опционально, по умолчанию 8000

# Linux/macOS
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/postgres
export SECRET_KEY=your-secret-key-here
export PORT=8000  # опционально, по умолчанию 8000
```

3. Запустите сервер:
```bash
# Порт будет взят из переменной окружения PORT или можно указать явно
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --reload
# или просто (порт по умолчанию 8000)
uvicorn main:app --reload
```

API будет доступен по адресу: http://localhost:8000 (или порт из переменной `PORT`)

## 📚 API Endpoints

### Авторизация (`/api/v3/auth`)

- `POST /auth/register` — регистрация нового пользователя
- `POST /auth/login` — вход (возвращает JWT токен)
- `GET /auth/me` — информация о текущем пользователе
- `PATCH /auth/change-password` — смена пароля
- `GET /auth/admin/users` — список пользователей (только для админов)

### Задачи (`/api/v3/tasks`)

- `GET /tasks` — список всех задач пользователя
- `GET /tasks/{task_id}` — получить задачу по ID
- `POST /tasks/` — создать новую задачу
- `PUT /tasks/{task_id}` — обновить задачу
- `PATCH /tasks/{task_id}/complete` — отметить задачу выполненной
- `DELETE /tasks/{task_id}` — удалить задачу
- `GET /tasks/quadrant/{Q1|Q2|Q3|Q4}` — задачи по квадранту
- `GET /tasks/status/{completed|pending}` — задачи по статусу
- `GET /tasks/search?q=keyword` — поиск задач
- `GET /tasks/today` — задачи с дедлайном на сегодня

### Статистика (`/api/v3/stats`)

- `GET /stats` — общая статистика (по квадрантам, статусам)
- `GET /stats/deadlines` — список задач с дедлайнами
- `GET /stats/timing` — статистика по срокам выполнения

### Сервисные

- `GET /` — информация о API
- `GET /health` — проверка здоровья API и подключения к БД
- `GET /docs` — Swagger UI документация
- `GET /redoc` — ReDoc документация

## 🔐 Аутентификация

API использует JWT токены. После успешного входа через `/auth/login` токен нужно передавать в заголовке:
```
Authorization: Bearer <your-token>
```

## 📊 Матрица Эйзенхауэра

Задачи автоматически распределяются по квадрантам:
- **Q1** — важно + срочно (дедлайн ≤ 3 дней)
- **Q2** — важно + не срочно (дедлайн > 3 дней)
- **Q3** — не важно + срочно (дедлайн ≤ 3 дней)
- **Q4** — не важно + не срочно (дедлайн > 3 дней)

Срочность пересчитывается автоматически планировщиком каждый день в 09:00 UTC.

## 🗄️ База данных

Используется PostgreSQL. Схема БД создаётся автоматически при первом запуске через SQLAlchemy или через скрипт `db/init.sql` при инициализации Docker контейнера.

### Модели

- **User** — пользователи системы (id, nickname, email, hashed_password, role)
- **Task** — задачи (id, title, description, is_important, is_urgent, quadrant, completed, deadline_at, user_id)

## 🔧 Переменные окружения

- `DATABASE_URL` — строка подключения к PostgreSQL (обязательно)
- `SECRET_KEY` — секретный ключ для JWT токенов (обязательно)
- `PORT` — порт для запуска FastAPI сервера (опционально, по умолчанию 8000)
- `HOST` — хост для запуска сервера (опционально, по умолчанию 0.0.0.0)

**Примечание:** Порт также можно задать через переменную `BACKEND_PORT` в `.env` файле корня проекта (используется в Docker Compose).

## 📝 Примеры использования

### Регистрация
```bash
curl -X POST "http://localhost:8000/api/v3/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"nickname": "user1", "email": "user@example.com", "password": "password123"}'
```

### Вход
```bash
curl -X POST "http://localhost:8000/api/v3/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=user@example.com&password=password123"
```

### Создание задачи
```bash
curl -X POST "http://localhost:8000/api/v3/tasks/" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "Новая задача", "is_important": true, "deadline_at": "2025-12-31T18:00:00Z"}'
```
