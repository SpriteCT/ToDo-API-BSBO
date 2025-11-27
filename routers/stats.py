from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models import Task
from database import get_async_session


router = APIRouter(
    prefix="/stats",
    tags=["statistics"],
)


@router.get("/", response_model=dict)
async def get_tasks_stats(
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    result = await db.execute(select(Task))
    tasks = result.scalars().all()

    total_tasks = len(tasks)
    by_quadrant = {"Q1": 0, "Q2": 0, "Q3": 0, "Q4": 0}
    by_status = {"completed": 0, "pending": 0}

    for task in tasks:
        if task.quadrant in by_quadrant:
            by_quadrant[task.quadrant] += 1
        if task.completed:
            by_status["completed"] += 1
        else:
            by_status["pending"] += 1

    return {
        "total_tasks": total_tasks,
        "by_quadrant": by_quadrant,
        "by_status": by_status,
    }

@router.get("/deadlines", response_model=list[dict])
async def get_pending_deadlines(
    db: AsyncSession = Depends(get_async_session),
) -> list[dict]:
    result = await db.execute(
        select(Task).where(Task.completed.is_(False))
    )
    tasks = result.scalars().all()

    today = datetime.now().date()
    data = []
    for task in tasks:
        if task.deadline_at is None:
            continue
         
        days_left = (task.deadline_at.date() - today).days
        data.append(
            {
                "title": task.title,
                "description": task.description,
                "created_at": task.created_at,
                "days_left": days_left,
            }
        )
    return data