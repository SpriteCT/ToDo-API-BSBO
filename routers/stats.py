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
