from fastapi import APIRouter, HTTPException, Query, status
from typing import List
from datetime import datetime
from schemas import TaskCreate, TaskUpdate, TaskResponse
from database import get_async_session
from models.tasks import Task, calc_quadrant
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
    responses={404: {"description" : "Task not found"}},
)

@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task: TaskCreate,
    db: AsyncSession = Depends(get_async_session),
) -> TaskResponse:
    quadrant = calc_quadrant(task.is_important, task.deadline_at)

    new_task = Task(
        title=task.title,
        description=task.description,
        is_important=task.is_important,
        quadrant=quadrant,
        completed=False,
        deadline_at=task.deadline_at,
    )

    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)
    return new_task


@router.get("", response_model=List[TaskResponse])
async def get_all_tasks(
    db: AsyncSession = Depends(get_async_session)) -> List[TaskResponse]:
    result =   await db.execute(select(Task))
    tasks = result.scalars().all()
    return tasks


@router.get("/quadrant/{quadrant}", response_model=List[TaskResponse])
async def get_tasks_by_quadrant(
    quadrant: str,
    db: AsyncSession = Depends(get_async_session),
) -> List[TaskResponse]:
    if quadrant not in ["Q1", "Q2", "Q3", "Q4"]:
        raise HTTPException(
            status_code=400,
            detail="Неверный квадрант. Используйте: Q1, Q2, Q3, Q4",  # текст для пользователя
        )

    # SELECT * FROM tasks WHERE quadrant = 'Q1'
    result = await db.execute(
        select(Task).where(Task.quadrant == quadrant)
    )
    tasks = result.scalars().all()
    return tasks


@router.get("/status/{status}", response_model=List[TaskResponse])
async def get_tasks_by_status(
    status: str,
    db: AsyncSession = Depends(get_async_session),
) -> List[TaskResponse]:
    if status not in ["completed", "pending"]:
        raise HTTPException(
            status_code=404,
            detail="Недопустимый статус. Используйте: completed или pending"
        )

    is_completed = (status == "completed")

    # SELECT * FROM tasks WHERE completed = True/False
    result = await db.execute(
        select(Task).where(Task.completed == is_completed)
    )
    tasks = result.scalars().all()

    return tasks


@router.get("/search", response_model=List[TaskResponse])
async def search_tasks(
    q: str = Query(..., min_length=2),
    db: AsyncSession = Depends(get_async_session),
) -> List[TaskResponse]:
    keyword = f"%{q.lower()}%"  # %keyword% для LIKE

    # SELECT * FROM tasks
    # WHERE LOWER(title) LIKE '%keyword%'
    #   OR LOWER(description) LIKE '%keyword%'
    result = await db.execute(
        select(Task).where(
            (Task.title.ilike(keyword)) |
            (Task.description.ilike(keyword))
        )
    )
    tasks = result.scalars().all()

    if not tasks:
        raise HTTPException(
            status_code=404,
            detail="По данному запросу ничего не найдено"
        )

    return tasks

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task_by_id(
    task_id: int,
    db: AsyncSession = Depends(get_async_session),
) -> TaskResponse:
    # SELECT * FROM tasks WHERE id = task_id
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )

    # Получаем одну задачу или None
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    return task

@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int,
    task_update: TaskUpdate,
    db: AsyncSession = Depends(get_async_session),
) -> TaskResponse:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    update_data = task_update.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(task, field, value)

    if "is_important" in update_data or "deadline_at" in update_data:
        task.quadrant = calc_quadrant(task.is_important, task.deadline_at)

    await db.commit()
    await db.refresh(task)
    return task



@router.patch("/{task_id}/complete", response_model=TaskResponse)
async def complete_task(
    task_id: int,
    db: AsyncSession = Depends(get_async_session),
) -> TaskResponse:
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    task.completed = True
    task.completed_at = datetime.now()

    await db.commit()
    await db.refresh(task)

    return task


@router.delete("/{task_id}", status_code=status.HTTP_200_OK)
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    # Сохраняем информацию для ответа
    deleted_task_info = {
        "id": task.id,
        "title": task.title,
    }

    await db.delete(task)   # Помечаем для удаления
    await db.commit()       # DELETE FROM tasks WHERE id = task_id

    return {
        "message": "Задача успешно удалена",
        "id": deleted_task_info["id"],
        "title": deleted_task_info["title"],
    }

