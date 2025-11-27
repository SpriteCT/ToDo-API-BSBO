from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from database import Base
from datetime import datetime

class Task(Base):
    __tablename__ = "tasks"
    id = Column(
        Integer,
        primary_key=True, # Первичный ключ
        index=True, # Создать индекс для быстрого поиска
        autoincrement=True # Автоматическая генерация
    )
    title = Column(
    Text, # Text = текст неограниченной длины
    nullable=False # Не может быть NULL
    )

    description = Column(
        Text,
        nullable=True # Может быть NULL
    )

    is_important = Column(
        Boolean,
        nullable=False,
        default=False # По умолчанию False
    )

    is_urgent = Column(
    Boolean,
    nullable=False,
    default=False
    )  

    quadrant = Column(
    String(2), # Максимум 2 символа: "Q1", "Q2", "Q3", "Q4"
    nullable=False
    )

    completed = Column(
        Boolean,
        nullable=False,
        default=False
    )

    created_at = Column(
        DateTime(timezone=True), # С поддержкой часовых поясов
        server_default=func.now(), # Автоматически текущее время
        nullable=False
    )

    completed_at = Column(
        DateTime(timezone=True),
        nullable=True # NULL пока задача не завершена
    )

    deadline_at = Column(
        DateTime(timezone=True),
        nullable=False
    )

def __repr__(self) -> str:
    return f"<Task(id={self.id}, title='{self.title}', quadrant='{self.quadrant}')>"

def to_dict(self) -> dict:
    return {
        "id": self.id,
        "title": self.title,
        "description": self.description,
        "is_important": self.is_important,
        "is_urgent": self.is_urgent,
        "quadrant": self.quadrant,
        "completed": self.completed,
        "created_at": self.created_at,
        "completed_at": self.completed_at
 }

def is_urgent_from_deadline(deadline_at: datetime) -> bool:
    days_left = (deadline_at.date() - datetime.utcnow().date()).days 
    return days_left <= 3


def calc_quadrant(is_important: bool, deadline_at: datetime) -> str:
    urgent = is_urgent_from_deadline(deadline_at)
    if is_important and urgent:
        return "Q1"
    elif is_important and not urgent:
        return "Q2"
    elif not is_important and urgent:
        return "Q3"
    else:
        return "Q4"
