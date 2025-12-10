from pydantic import BaseModel, Field, computed_field
from typing import Optional
from datetime import datetime
from utils import is_urgent_from_deadline

# Базовая схема для Task.
# Все поля, которые есть в нашей "базе данных" tasks_db
class TaskBase(BaseModel):
    title: str = Field(
        ...,  # троеточие означает "обязательное поле"
        min_length=3,
        max_length=100,
        description="Название задачи"
    )
    description: Optional[str] = Field(
        None,  # None = необязательное поле
        max_length=500,
        description="Описание задачи"
    )
    is_important: bool = Field(
        ...,
        description="Важность задачи"
    )
    deadline_at: Optional[datetime] = Field(
        None,
        description="Крайний срок выполнения задачи"
    )


# Схема для создания новой задачи
# Наследует все поля от TaskBase
class TaskCreate(TaskBase):
    pass


# Схема для обновления задачи (используется в PUT)
# Все поля опциональные, т.к. мы можем захотеть обновить только title или status
class TaskUpdate(BaseModel):
    title: Optional[str] = Field(
        None,
        min_length=3,
        max_length=100,
        description="Новое название задачи"
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Новое описание"
    )
    is_important: Optional[bool] = Field(
        None,
        description="Новая важность"
    )
    is_urgent: Optional[bool] = Field(
        None,
        description="Новая срочность"
    )
    completed: Optional[bool] = Field(
        None,
        description="Статус выполнения"
    )
    deadline_at: Optional[datetime] = Field(
        None,
        description="Новый крайний срок"
    )


# Модель для ответа (TaskResponse)
# При ответе сервер возвращает полную информацию о задаче,
# включая сгенерированные поля: id, quadrant, created_at, etc.
class TaskResponse(TaskBase):
    id: int = Field(
        ...,
        description="Уникальный идентификатор задачи",
        examples=[1]
    )
    quadrant: str = Field(
        ...,
        description="Квадрант матрицы Эйзенхауэра (Q1, Q2, Q3, Q4)",
        examples=["Q1"]
    )
    completed: bool = Field(
        default=False,
        description="Статус выполнения задачи"
    )
    created_at: datetime = Field(
        ...,
        description="Дата и время создания задачи"
    )

    @computed_field
    @property
    def days_left(self) -> int:
        if self.deadline_at is None:
            return None
        return (self.deadline_at.date() - datetime.utcnow().date()).days
    
    @computed_field
    @property
    def is_urgent(self) -> bool:

        return is_urgent_from_deadline(self.deadline_at)
    
    class Config:  # Config класс для работы с ORM (понадобится после подключения СУБД)
        from_attributes = True

class TimingStatsResponse(BaseModel):
    completed_on_time: int = Field(
        ...,
        description="Количество задач, завершенных в срок"
    )
    completed_late: int = Field(
        ...,
        description="Количество задач, завершенных с нарушением сроков"
    )
    on_plan_pending: int = Field(
        ...,
        description="Количество задач в работе, выполняемых в соответствии с планом"
    )
    overtime_pending: int = Field(
        ...,
        description="Количество просроченных незавершенных задач"
    )
