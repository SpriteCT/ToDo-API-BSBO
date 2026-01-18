# ToDo API + Telegram Bot

Система управления задачами с использованием матрицы Эйзенхауэра, состоящая из:
- **Backend API** (FastAPI + PostgreSQL)
- **Telegram Bot** (aiogram)

## 📁 Структура проекта

```
.
├── docker-compose.yml      # Оркестрация всех сервисов
├── .env                     # Переменные окружения (создать вручную)
├── backend/                 # Backend API (FastAPI)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── models/              # SQLAlchemy модели
│   ├── routers/             # API маршруты
│   └── ...
├── bot/                     # Telegram бот
│   ├── Dockerfile
│   ├── bot.py               # Основной код бота
│   ├── api_client.py        # HTTP клиент для API
│   └── config.py            # Конфигурация
└── db/                      # SQL скрипты
    └── init.sql             # Инициализация БД
```

## 🚀 Быстрый старт

### 1. Создайте файл `.env` в корне проекта:

```bash
TELEGRAM_BOT_TOKEN=ваш_токен_от_BotFather
BACKEND_PORT=8000  # Порт для Backend API (опционально, по умолчанию 8000)
```

### 2. Запустите все сервисы через Docker Compose:

```bash
docker-compose up --build
```

После запуска будут доступны:
- **Backend API**: http://localhost:8000 (или порт из `BACKEND_PORT`)
- **API документация**: http://localhost:8000/docs
- **PostgreSQL**: localhost:5432
- **Telegram Bot**: работает автоматически

## 📋 Компоненты системы

### Backend API

REST API на FastAPI с эндпоинтами:
- `/api/v3/auth` — авторизация и регистрация
- `/api/v3/tasks` — управление задачами
- `/api/v3/stats` — статистика

**Подробнее**: см. [backend/README.md](backend/README.md)

### Telegram Bot

Бот для управления задачами через Telegram с командами:
- `/start`, `/help` — справка
- `/register`, `/login`, `/logout` — авторизация
- `/timezone <сдвиг>` — установка часового пояса
- `/change_password` — смена пароля
- `/me` — информация о пользователе
- `/tasks` — список всех задач
- `/today` — задачи на сегодня
- `/search <текст>` — поиск задач
- `/newtask` — создать задачу
- `/edittask` — изменить задачу
- `/complete <id>` — завершить задачу
- `/delete <id>` — удалить задачу

**Напоминания**: бот автоматически напоминает о задачах с приближающимся дедлайном (0-1 день).

## 🗄️ База данных

PostgreSQL 16 с автоматической инициализацией через `db/init.sql`:
- Таблица `users` — пользователи системы
- Таблица `tasks` — задачи пользователей
- ENUM тип `userrole` — роли пользователей (user, admin)

## 🔧 Разработка

### Локальный запуск без Docker

1. **Backend** (см. [backend/README.md](backend/README.md))
2. **Bot**: 
   ```bash
   cd bot
   pip install -r ../backend/requirements.txt aiogram
   python -m bot.bot
   ```

### Переменные окружения

**В `.env` файле (корень проекта):**
- `TELEGRAM_BOT_TOKEN` — токен Telegram бота (обязательно)
- `BACKEND_PORT` — порт для Backend API (опционально, по умолчанию 8000)

**В Docker Compose (задаются автоматически):**
- `DATABASE_URL` — строка подключения к PostgreSQL
- `SECRET_KEY` — секретный ключ для JWT
- `PORT` — порт для запуска FastAPI сервера (берётся из `BACKEND_PORT`)
- `HOST` — хост для запуска сервера (по умолчанию 0.0.0.0)

## 📝 Матрица Эйзенхауэра

Задачи автоматически распределяются по квадрантам:
- **Q1** — важно + срочно
- **Q2** — важно + не срочно
- **Q3** — не важно + срочно
- **Q4** — не важно + не срочно

Срочность определяется автоматически: задача считается срочной, если до дедлайна ≤ 3 дней.

## 🛠️ Технологии

- **Backend**: FastAPI, SQLAlchemy (async), PostgreSQL, APScheduler
- **Bot**: aiogram 3.x, httpx
- **Infrastructure**: Docker, Docker Compose

## 📄 Лицензия

Учебный проект.

