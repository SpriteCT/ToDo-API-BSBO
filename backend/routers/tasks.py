from fastapi import APIRouter, HTTPException, Query, status
from typing import List
from datetime import datetime
from dependencies import get_current_user
from models.user import User
from schemas import TaskCreate, TaskUpdate, TaskResponse
from database import get_async_session
from models.tasks import Task
from utils import calc_quadrant
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func


router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
    responses={404: {"description": "Task not found"}},
)


@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task: TaskCreate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> TaskResponse:
    # Определяем квадрант
    quadrant = calc_quadrant(task.is_important, task.deadline_at)

    new_task = Task(
        title=task.title,
        description=task.description,
        is_important=task.is_important,
        quadrant=quadrant,
        deadline_at=task.deadline_at,
        completed=False,
        user_id=current_user.id,
    )

    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)

    return new_task


@router.get("", response_model=List[TaskResponse])
async def get_all_tasks(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> List[TaskResponse]:
    # Если пользователь - admin, показываем все задачи
    if current_user.role.value == "admin":
        result = await db.execute(select(Task))
    else:
        # Обычные пользователи видят только свои задачи
        result = await db.execute(
            select(Task).where(Task.user_id == current_user.id)
        )

    tasks = result.scalars().all()

    return tasks


@router.get("/quadrant/{quadrant}", response_model=List[TaskResponse])
async def get_tasks_by_quadrant(
    quadrant: str,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> List[TaskResponse]:
    """Получить задачи пользователя по квадрату"""

    if quadrant not in ["Q1", "Q2", "Q3", "Q4"]:
        raise HTTPException(
            status_code=400,
            detail="Неверный квадрант. Используйте: Q1, Q2, Q3, Q4",
        )

    # Администраторы видят все, пользователи - только свои
    if current_user.role.value == "admin":
        result = await db.execute(
            select(Task).where(Task.quadrant == quadrant)
        )
    else:
        result = await db.execute(
            select(Task).where(
                Task.quadrant == quadrant,
                Task.user_id == current_user.id,
            )
        )

    tasks = result.scalars().all()
    return tasks


@router.get("/status/{status}", response_model=List[TaskResponse])
async def get_tasks_by_status(
    status: str,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> List[TaskResponse]:
    if status not in ["completed", "pending"]:
        raise HTTPException(
            status_code=400,
            detail="Недопустимый статус. Используйте: completed или pending",
        )

    is_completed = status == "completed"

    if current_user.role.value == "admin":
        result = await db.execute(
            select(Task).where(Task.completed == is_completed)
        )
    else:
        result = await db.execute(
            select(Task).where(
                Task.completed == is_completed,
                Task.user_id == current_user.id,
            )
        )

    tasks = result.scalars().all()
    return tasks


@router.get("/search", response_model=List[TaskResponse])
async def search_tasks(
    q: str = Query(..., min_length=2),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> List[TaskResponse]:
    keyword = f"%{q.lower()}%"

    if current_user.role.value == "admin":
        result = await db.execute(
            select(Task).where(
                Task.title.ilike(keyword)
                | Task.description.ilike(keyword)
            )
        )
    else:
        result = await db.execute(
            select(Task).where(
                Task.user_id == current_user.id,
                Task.title.ilike(keyword)
                | Task.description.ilike(keyword),
            )
        )

    tasks = result.scalars().all()
    if not tasks:
        raise HTTPException(
            status_code=404,
            detail="По данному запросу ничего не найдено",
        )

    return tasks


@router.get("/today", response_model=List[TaskResponse])
async def get_tasks_due_today(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> List[TaskResponse]:
    today = datetime.utcnow().date()  # текущая дата в UTC

    # Админ видит все задачи на сегодня, пользователь — только свои
    if current_user.role.value == "admin":
        stmt = select(Task).where(func.date(Task.deadline_at) == today)
    else:
        stmt = select(Task).where(
            func.date(Task.deadline_at) == today,
            Task.user_id == current_user.id,
        )

    result = await db.execute(stmt)
    tasks = result.scalars().all()

    if not tasks:
        raise HTTPException(
            status_code=404,
            detail="На сегодня задач не найдено",
        )

    return tasks


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task_by_id(
    task_id: int,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> TaskResponse:
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=404,
            detail="Задача не найдена",
        )

    if current_user.role.value != "admin" and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к этой задаче",
        )

    return task


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int,
    task_update: TaskUpdate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> TaskResponse:
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=404,
            detail="Задача не найдена",
        )
    # Проверка прав доступа
    if current_user.role.value != "admin" and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к этой задаче",
        )
    update_data = task_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)

    # Пересчитываем срочность и квадрант
    if "is_important" in update_data or "deadline_at" in update_data:
        task.quadrant = calc_quadrant(task.is_important, task.deadline_at)

    await db.commit()
    await db.refresh(task)

    return task


@router.patch("/{task_id}/complete", response_model=TaskResponse)
async def complete_task(
    task_id: int,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> TaskResponse:
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=404,
            detail="Задача не найдена",
        )

    # Проверка прав доступа
    if current_user.role.value != "admin" and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к этой задаче",
        )

    task.completed = True
    task.completed_at = datetime.now()

    await db.commit()
    await db.refresh(task)

    return task


@router.delete("/{task_id}", status_code=status.HTTP_200_OK)
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=404,
            detail="Задача не найдена",
        )

    # Проверка прав доступа
    if current_user.role.value != "admin" and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к этой задаче",
        )

    deleted_task_info = {
        "id": task.id,
        "title": task.title,
    }

    await db.delete(task)
    await db.commit()

    return {
        "message": "Задача успешно удалена",
        "id": deleted_task_info["id"],
        "title": deleted_task_info["title"],
    }


