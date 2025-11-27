# ToDo лист API (матрица Эйзенхауэра)

Небольшое демонстрационное приложение на FastAPI для управления задачами с распределением по квадрантам Эйзенхауэра и хранением данных в PostgreSQL (Supabase).

## Кратко

- Веб‑API реализовано в файле [`main.py`](main.py).
- Работа с БД организована через асинхронный SQLAlchemy в файле [`database.py`](database.py).
- Описание таблиц (в т.ч. модели `Task` с полем `deadline_at`) — в каталоге [`models`](models).
- Схемы Pydantic для запросов и ответов — в [`schemas.py`](schemas.py).
- Маршруты:
  - [`routers/tasks.py`](routers/tasks.py) — CRUD по задачам.
  - [`routers/stats.py`](routers/stats.py) — агрегированная статистика и анализ дедлайнов.

## Требования

- Python 3.11+ (рекомендуется)
- PostgreSQL (например, Supabase)
- Зависимости в [`requirements.txt`](requirements.txt)

## Установка и запуск

1. Создать виртуальное окружение:

```

python -m venv .venv

# Windows

.venv\Scripts\activate

# Linux / macOS

source .venv/bin/activate

```

2. Установить зависимости:

```

pip install -r requirements.txt

```

3. Указать строку подключения к БД в переменной окружения `DATABASE_URL`
(используется в `database.py`).

4. Запустить сервер разработки:

```

uvicorn main:app --reload

```

Документация будет доступна по адресам:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Модель задачи и логика срочности

Модель `Task` содержит, в том числе, следующие поля:

- `title` — заголовок задачи;
- `description` — описание;
- `is_important` — важность;
- `deadline_at` — плановый дедлайн выполнения;
- `quadrant` — квадрант матрицы Эйзенхауэра (`Q1`–`Q4`);
- `completed` — статус выполнения;
- `created_at` / `completed_at` — даты создания и завершения.

Срочность задачи вычисляется автоматически на основе `deadline_at`:

- «Срочно» — если от сегодняшней даты до дедлайна ≤ 3 дней;
- «Не срочно» — если от сегодняшней даты до дедлайна > 3 дней.

Комбинация важности и срочности определяет квадрант:

- важно + срочно → `Q1`;
- важно + не срочно → `Q2`;
- не важно + срочно → `Q3`;
- не важно + не срочно → `Q4`.

Pydantic‑схема ответа `TaskResponse` дополнительно содержит вычисляемое поле `days_left` — количество дней от сегодняшней даты до дедлайна.

## Основные эндпоинты

### Сервисные

- `GET /` — информация о приложении.
- `GET /health` — проверка «здоровья» API и подключения к БД.

### Задачи (`/api/v2/tasks`)

- `GET /api/v2/tasks` — список всех задач.
- `GET /api/v2/tasks/{task_id}` — задача по ID.
- `GET /api/v2/tasks/quadrant/{Q1|Q2|Q3|Q4}` — задачи по квадранту.
- `GET /api/v2/tasks/status/{completed|pending}` — задачи по статусу выполнения.
- `GET /api/v2/tasks/search?q=keyword` — поиск по названию/описанию.
- `POST /api/v2/tasks` — создание задачи  
(передаются `title`, `description`, `is_important`, `deadline_at`; срочность и квадрант рассчитываются автоматически).
- `PUT /api/v2/tasks/{task_id}` — полное обновление задачи  
(при изменении `is_important` или `deadline_at` квадрант пересчитывается).
- `PATCH /api/v2/tasks/{task_id}/complete` — отметить задачу выполненной.
- `DELETE /api/v2/tasks/{task_id}` — удалить задачу.

### Статистика (`/api/v2/stats`)

- `GET /api/v2/stats` — общая статистика:
- общее количество задач (`total_tasks`);
- распределение по квадрантам (`by_quadrant`);
- распределение по статусам (`by_status`).

- `GET /api/v2/stats/deadlines` — статистика по задачам в статусе `pending`:
- `title` — название;
- `description` — описание;
- `created_at` — дата создания;
- `days_left` — оставшийся срок до дедлайна (в днях).
```