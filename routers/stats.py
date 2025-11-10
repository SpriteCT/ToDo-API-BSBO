from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException
from database import tasks_db


router = APIRouter(
    prefix="/stats",
    tags=["stats"]
)


@router.get("/")
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