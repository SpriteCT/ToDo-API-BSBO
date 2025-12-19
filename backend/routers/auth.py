from typing import Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from database import get_async_session
from models.tasks import Task
from models.user import User, UserRole
from schemas_auth import UserCreate, UserResponse, Token
from auth_utils import verify_password, get_password_hash, create_access_token
from dependencies import get_current_user

router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_async_session),
):
    # Проверяем, не занят ли email
    result = await db.execute(
        select(User).where(User.email == user_data.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь с таким email уже существует",
        )

    # Проверяем, не занят ли nickname
    result = await db.execute(
        select(User).where(User.nickname == user_data.nickname)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь с таким никнеймом уже существует",
        )

    # Создаем нового пользователя
    new_user = User(
        nickname=user_data.nickname,
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        role=UserRole.USER,
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return new_user


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_async_session),
):
    # Ищем пользователя по email (username в форме = email)
    result = await db.execute(
        select(User).where(User.email == form_data.username)
    )
    user = result.scalar_one_or_none()

    # Проверяем пользователя и пароль
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Создаем JWT токен
    access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role.value}
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
):
    return current_user


@router.patch("/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    old_password: str,
    new_password: str,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> Dict[str, str]:
    # Проверяем старый пароль
    if not verify_password(old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Старый пароль указан неверно",
        )

    # Хешируем и сохраняем новый пароль
    current_user.hashed_password = get_password_hash(new_password)
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)

    return {"message": "Пароль успешно изменён"}


@router.get("/admin/users", response_model=List[dict])
async def get_users_with_task_counts(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> List[dict]:
    # Доступ только для админов
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ запрещён",
        )

    # SELECT users.*, COUNT(tasks.id) AS task_count
    # FROM users LEFT JOIN tasks ON tasks.user_id = users.id
    # GROUP BY users.id;
    stmt = (
        select(
            User.id,
            User.nickname,
            User.email,
            User.role,
            func.count(Task.id).label("task_count"),
        )
        .outerjoin(Task, Task.user_id == User.id)
        .group_by(User.id)
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "id": row.id,
            "nickname": row.nickname,
            "email": row.email,
            "role": row.role.value,
            "task_count": row.task_count,
        }
        for row in rows
    ]


