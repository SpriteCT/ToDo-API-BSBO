# Главный файл приложения
from fastapi import FastAPI, HTTPException
from typing import List, Dict, Any
from datetime import datetime

app = FastAPI(
    title="ToDo лист API",
    description="API для управления задачами с использованием матрицы Эйзенхауэра",
    version="1.0.0",
    name="Саранцев Антон Игоревич"
)

# Временное хранилище (позже будет заменено на PostgreSQL)
tasks_db: List[Dict[str, Any]] = [
    {
        "id": 1,
        "title": "Сдать проект по FastAPI",
        "description": "Завершить разработку API и написать документацию",
        "is_important": True,
        "is_urgent": True,
        "quadrant": "Q1",
        "completed": False,
        "created_at": datetime.now()
    },
    {
        "id": 2,
        "title": "Изучить SQLAlchemy",
        "description": "Прочитать документацию и попробовать примеры",
        "is_important": True,
        "is_urgent": False,
        "quadrant": "Q2",
        "completed": False,
        "created_at": datetime.now()
    },
    {
        "id": 3,
        "title": "Сходить на лекцию",
        "description": None,
        "is_important": False,
        "is_urgent": True,
        "quadrant": "Q3",
        "completed": False,
        "created_at": datetime.now()
    },
    {
        "id": 4,
        "title": "Посмотреть сериал",
        "description": "Новый сезон любимого сериала",
        "is_important": False,
        "is_urgent": False,
        "quadrant": "Q4",
        "completed": True,
        "created_at": datetime.now()
    },
]


@app.get("/")
async def welcome() -> dict:
    return {
        "title": app.title,
        "description": app.description,
        "version": app.version,
        "docs_url": app.docs_url,
        "redoc_url": app.redoc_url,
        "openapi_url": app.openapi_url,
        "routes_count": len(app.routes)
    }


@app.get("/tasks")
async def get_all_tasks() -> dict:
    """Возвращает все задачи и их количество"""
    return {
        "count": len(tasks_db),
        "tasks": tasks_db
    }


@app.get("/tasks/quadrant/{quadrant}")
async def get_tasks_by_quadrant(quadrant: str) -> dict:
    """Возвращает задачи по выбранному квадранту матрицы Эйзенхауэра"""
    if quadrant not in ["Q1", "Q2", "Q3", "Q4"]:
        raise HTTPException(
            status_code=400,
            detail="Неверный квадрант. Используйте: Q1, Q2, Q3, Q4"
        )

    filtered_tasks = [
        task
        for task in tasks_db
        if task["quadrant"] == quadrant
    ]

    return {
        "quadrant": quadrant,
        "count": len(filtered_tasks),
        "tasks": filtered_tasks
    }

@app.get("/tasks/stats")
async def get_tasks_stats() -> dict:
    """Возвращает статистику по задачам"""
    total_tasks = len(tasks_db)

    # Подсчёт по квадрантам
    by_quadrant = {
        "Q1": len([t for t in tasks_db if t["quadrant"] == "Q1"]),
        "Q2": len([t for t in tasks_db if t["quadrant"] == "Q2"]),
        "Q3": len([t for t in tasks_db if t["quadrant"] == "Q3"]),
        "Q4": len([t for t in tasks_db if t["quadrant"] == "Q4"]),
    }

    # Подсчёт по статусу
    by_status = {
        "completed": len([t for t in tasks_db if t["completed"]]),
        "pending": len([t for t in tasks_db if not t["completed"]])
    }

    return {
        "total_tasks": total_tasks,
        "by_quadrant": by_quadrant,
        "by_status": by_status
    }

@app.get("/tasks/status/{status}")
async def get_tasks_by_status(status: str) -> dict:
    """Возвращает задачи по статусу выполнения (completed или pending)"""
    if status not in ["completed", "pending"]:
        raise HTTPException(
            status_code=404,
            detail="Неверный статус. Используйте: completed или pending"
        )

    is_completed = status == "completed"

    filtered_tasks = [
        task for task in tasks_db if task["completed"] == is_completed
    ]

    return {
        "status": status,
        "count": len(filtered_tasks),
        "tasks": filtered_tasks
    }

@app.get("/tasks/search")
async def search_tasks(q: str) -> dict:
    """Поиск задач по ключевому слову в названии или описании"""
    # Проверка длины запроса
    if len(q.strip()) < 2:
        raise HTTPException(
            status_code=400,
            detail="Ключевое слово должно содержать минимум 2 символа"
        )

    keyword = q.lower()
    found_tasks = [
        task for task in tasks_db
        if keyword in task["title"].lower() or
           (task["description"] and keyword in task["description"].lower())
    ]

    if not found_tasks:
        raise HTTPException(
            status_code=404,
            detail=f"Задачи, содержащие '{q}', не найдены"
        )

    return {
        "query": q,
        "count": len(found_tasks),
        "tasks": found_tasks
    }


@app.get("/tasks/{task_id}")
async def get_task_by_id(task_id: int) -> dict:
    """Возвращает задачу по её ID"""
    task = next((task for task in tasks_db if task["id"] == task_id), None)

    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"Задача с ID {task_id} не найдена"
        )

    return task



