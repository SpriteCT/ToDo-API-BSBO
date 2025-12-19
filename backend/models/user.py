from sqlalchemy import Column, Integer, String, Enum
from sqlalchemy.orm import relationship
from database import Base
import enum


class UserRole(enum.Enum):
    USER = "user"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    nickname = Column(
        String(50),
        unique=True,      # Никнейм должен быть уникальным
        nullable=False,
        index=True,       # Индекс для быстрого поиска
    )

    email = Column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )

    hashed_password = Column(
        String(255),      # Хешированный пароль (НЕ храним в открытом виде!!)
        nullable=False,
    )

    role = Column(
        Enum(
            UserRole,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=UserRole.USER,   # По умолчанию — обычный пользователь
    )

    tasks = relationship(
        "Task",
        back_populates="owner",
        cascade="all, delete-orphan",  # Удалять задачи при удалении пользователя
    )

    def __repr__(self):
        return f"<User(id={self.id}, nickname='{self.nickname}', role='{self.role.value}')>"


