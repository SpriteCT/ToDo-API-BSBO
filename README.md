# ToDo лист API (матрица Эйзенхауэра)

Небольшое демонстрационное приложение на FastAPI для управления задачами с распределением по квадрантам Эйзенхауэра.

Кратко:
- Веб‑API реализовано в файле [main.py](main.py).
- Временное хранилище задач — переменная `tasks_db` в [main.py](main.py).
- В будущем планируется подключение БД — см. [database.py](database.py), [models.py](models.py), [schemas.py](schemas.py).

Требования
- Python 3.8+ (рекомендуется 3.11)
- Зависимости в [requirements.txt](requirements.txt)

Установка и запуск
1. Создать виртуальное окружение:
```
python -m venv .venv
source .venv/bin/activate
```
2. Установить зависимости:
```
pip install -r requirements.txt
```
3. Запустить сервер разработки:
```
uvicorn main:app --reload
```

Основные эндпоинты
- GET / — информация о приложении (использует [`app`](main.py))
- GET /tasks — все задачи
- GET /tasks/{task_id} — задача по ID
- GET /tasks/quadrant/{Q1|Q2|Q3|Q4} — задачи по квадранту
- GET /tasks/status/{completed|pending} — задачи по статусу
- GET /tasks/search?q=keyword — поиск по названию/описанию
- GET /tasks/stats — статистика по задачам

