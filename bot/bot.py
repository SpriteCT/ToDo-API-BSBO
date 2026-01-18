import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
import re

import httpx
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from .api_client import ApiClient
from .config import TELEGRAM_BOT_TOKEN


# ---------- Состояния FSM ----------


class RegisterStates(StatesGroup):
    nickname = State()
    email = State()
    password = State()


class LoginStates(StatesGroup):
    email = State()
    password = State()


class ChangePasswordStates(StatesGroup):
    old_password = State()
    new_password = State()


class NewTaskStates(StatesGroup):
    title = State()
    description = State()
    is_important = State()
    deadline = State()


class EditTaskStates(StatesGroup):
    task_id = State()
    field = State()  # какое поле редактируем
    value = State()  # новое значение


class TimezoneStates(StatesGroup):
    offset = State()


class SearchStates(StatesGroup):
    query = State()


@dataclass
class UserSession:
    access_token: str
    email: str


# Память сессий бота в памяти процесса: chat_id -> UserSession
SESSIONS: Dict[int, UserSession] = {}

# Сдвиг часового пояса пользователя относительно UTC, в часах: chat_id -> offset
TIMEZONE_OFFSETS: Dict[int, int] = {}

# Время последней отправки напоминания для каждого пользователя: chat_id -> datetime
LAST_REMINDER_SENT: Dict[int, datetime] = {}


router = Router()
api_client = ApiClient()

# Глобальный bot instance (устанавливается в main())
_bot_instance: Optional[Bot] = None


def get_bot() -> Bot:
    """Получить экземпляр бота. Должен быть установлен через set_bot() перед использованием."""
    if _bot_instance is None:
        raise RuntimeError("Bot instance not set. Call set_bot() first.")
    return _bot_instance


def set_bot(bot: Bot) -> None:
    """Установить глобальный экземпляр бота."""
    global _bot_instance
    _bot_instance = bot


def _get_utc_offset_hours(chat_id: int) -> int:
    """Возвращает сдвиг часового пояса для чата в часах (по умолчанию +3)."""
    return TIMEZONE_OFFSETS.get(chat_id, 3)


def _local_to_utc(chat_id: int, dt_local: datetime) -> datetime:
    """Преобразует локальное время пользователя в UTC с учетом сохранённого сдвига."""
    offset = _get_utc_offset_hours(chat_id)
    dt_utc = dt_local - timedelta(hours=offset)
    return dt_utc.replace(tzinfo=timezone.utc)


def _utc_to_local(chat_id: int, dt_utc: datetime) -> datetime:
    """Преобразует время из UTC в локальное время пользователя."""
    if dt_utc is None:
        return None
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    offset = _get_utc_offset_hours(chat_id)
    return dt_utc + timedelta(hours=offset)


def _format_task(task: dict, chat_id: int) -> str:
    """Форматирует задачу для отображения в виде текста."""
    raw_deadline = task.get("deadline_at")
    if raw_deadline:
        try:
            dt_utc = datetime.fromisoformat(raw_deadline)
            dt_local = _utc_to_local(chat_id, dt_utc)
            deadline_str = dt_local.strftime("%Y-%m-%d %H:%M")
        except Exception:
            deadline_str = str(raw_deadline)
    else:
        deadline_str = "без дедлайна"

    status = "✅" if task.get("completed") else "⏳"
    quadrant = task.get("quadrant", "?")
    return (
        f"ID: {task.get('id')} {status}\n"
        f"Название: {task.get('title')}\n"
        f"Описание: {task.get('description') or '-'}\n"
        f"Квадрант: {quadrant}\n"
        f"Дедлайн: {deadline_str}\n"
    )


def _get_task_buttons(task: dict) -> InlineKeyboardMarkup:
    """Возвращает inline-кнопки для задачи (выполнить, редактировать)."""
    task_id = task.get('id')
    is_completed = task.get('completed', False)
    
    buttons = []
    if not is_completed:
        buttons.append([InlineKeyboardButton(text="✅ Выполнить", callback_data=f"complete_{task_id}")])
    buttons.append([InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_{task_id}")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _require_session(message: Message) -> Optional[UserSession]:
    chat_id = message.chat.id
    session = SESSIONS.get(chat_id)
    if not session:
        await message.answer(
            "Вы не авторизованы. Воспользуйтесь командами /register или /login."
        )
        return None
    return session


def _get_main_menu(chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Возвращает текст и клавиатуру главного меню в зависимости от авторизации."""
    is_authenticated = chat_id in SESSIONS
    
    if is_authenticated:
        text = "Привет! Я бот для управления задачами.\n\nВыберите действие из меню:"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Мои задачи", callback_data="tasks_all")],
            [
                InlineKeyboardButton(text="➕ Создать задачу", callback_data="newtask"),
                InlineKeyboardButton(text="📅 Задачи на сегодня", callback_data="today")
            ],
            [
                InlineKeyboardButton(text="🔍 Поиск", callback_data="search_prompt"),
                InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")
            ],
            [InlineKeyboardButton(text="ℹ️ О пользователе", callback_data="me")]
        ])
    else:
        text = (
            "Привет! Я бот для управления задачами.\n\n"
            "Для начала работы необходимо войти в систему."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔐 Регистрация", callback_data="register"),
                InlineKeyboardButton(text="🔑 Вход", callback_data="login")
            ]
        ])
    
    return text, keyboard


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    text, keyboard = _get_main_menu(message.chat.id)
    await message.answer(text, reply_markup=keyboard)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await cmd_start(message)


@router.message(Command("timezone"))
async def cmd_timezone(message: Message) -> None:
    """
    Установка часового пояса пользователя относительно UTC.
    Пример: /timezone +3  или  /timezone -5
    """
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Укажите сдвиг относительно UTC в часах.\n"
            "Пример: /timezone +3  или  /timezone -5"
        )
        return

    raw_offset = parts[1].strip().replace("UTC", "").replace("utc", "")
    try:
        offset = int(raw_offset)
    except ValueError:
        await message.answer(
            "Неверный формат. Используйте целое число часов, например: /timezone +3"
        )
        return

    if not -12 <= offset <= 14:
        await message.answer("Сдвиг должен быть в диапазоне от -12 до +14 часов.")
        return

    TIMEZONE_OFFSETS[message.chat.id] = offset
    sign = "+" if offset >= 0 else ""
    await message.answer(f"Часовой пояс сохранён: UTC{sign}{offset}.")


# ---------- Регистрация ----------


async def _start_register(message_or_query: Message | CallbackQuery, state: FSMContext) -> None:
    """Запускает процесс регистрации."""
    await state.set_state(RegisterStates.nickname)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Отмена", callback_data="back_to_main")]
    ])
    
    if isinstance(message_or_query, CallbackQuery):
        await state.update_data(edit_message_id=message_or_query.message.message_id, chat_id=message_or_query.message.chat.id)
        try:
            await message_or_query.message.edit_text("Введите ваш никнейм:", reply_markup=keyboard)
        except Exception:
            pass
        await message_or_query.answer()
    else:
        msg = await message_or_query.answer("Введите ваш никнейм:", reply_markup=keyboard)
        await state.update_data(edit_message_id=msg.message_id, chat_id=message_or_query.chat.id)


@router.message(Command("register"))
async def cmd_register(message: Message, state: FSMContext) -> None:
    await _start_register(message, state)


@router.message(RegisterStates.nickname)
async def register_nickname(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    edit_message_id = data.get("edit_message_id")
    chat_id = message.chat.id
    
    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except Exception:
        pass
    
    await state.update_data(nickname=message.text.strip())
    await state.set_state(RegisterStates.email)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Отмена", callback_data="back_to_main")]
    ])
    text = "Введите ваш email:"
    
    bot = get_bot()
    if edit_message_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
        except Exception:
            pass


@router.message(RegisterStates.email)
async def register_email(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    edit_message_id = data.get("edit_message_id")
    chat_id = message.chat.id
    
    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except Exception:
        pass
    
    email = message.text.strip()
    # Простая валидация email, чтобы не слать заведомо неверные данные на backend
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Отмена", callback_data="back_to_main")]
        ])
        text = "❌ Некорректный email. Введите адрес в формате name@example.com:"
        bot = get_bot()
        if edit_message_id:
            try:
                await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
            except Exception:
                pass
        return

    await state.update_data(email=email)
    await state.set_state(RegisterStates.password)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Отмена", callback_data="back_to_main")]
    ])
    text = "Введите пароль (минимум 6 символов):"
    
    bot = get_bot()
    if edit_message_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
        except Exception:
            pass


@router.message(RegisterStates.password)
async def register_password(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    edit_message_id = data.get("edit_message_id")
    chat_id = message.chat.id
    nickname = data["nickname"]
    email = data["email"]
    password = message.text.strip()

    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except Exception:
        pass

    try:
        await api_client.register_user(nickname=nickname, email=email, password=password)
    except Exception as e:  # httpx.HTTPError
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Назад в главное меню", callback_data="back_to_main")]
        ])
        text = f"❌ Ошибка регистрации: {e}"
        bot = get_bot()
        if edit_message_id:
            try:
                await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
            except Exception:
                pass
        await state.clear()
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Войти", callback_data="login")]
    ])
    text = "✅ Регистрация прошла успешно! Теперь выполните вход."
    bot = get_bot()
    if edit_message_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
        except Exception:
            pass
    await state.clear()


# ---------- Логин ----------


async def _start_login(message_or_query: Message | CallbackQuery, state: FSMContext) -> None:
    """Запускает процесс входа."""
    await state.set_state(LoginStates.email)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Отмена", callback_data="back_to_main")]
    ])
    
    if isinstance(message_or_query, CallbackQuery):
        await state.update_data(edit_message_id=message_or_query.message.message_id, chat_id=message_or_query.message.chat.id)
        try:
            await message_or_query.message.edit_text("Введите email:", reply_markup=keyboard)
        except Exception:
            pass
        await message_or_query.answer()
    else:
        msg = await message_or_query.answer("Введите email:", reply_markup=keyboard)
        await state.update_data(edit_message_id=msg.message_id, chat_id=message_or_query.chat.id)


@router.message(Command("login"))
async def cmd_login(message: Message, state: FSMContext) -> None:
    await _start_login(message, state)


@router.message(LoginStates.email)
async def login_email(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    edit_message_id = data.get("edit_message_id")
    chat_id = message.chat.id
    
    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except Exception:
        pass
    
    await state.update_data(email=message.text.strip())
    await state.set_state(LoginStates.password)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Отмена", callback_data="back_to_main")]
    ])
    text = "Введите пароль:"
    
    bot = get_bot()
    if edit_message_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
        except Exception:
            pass


@router.message(LoginStates.password)
async def login_password(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    edit_message_id = data.get("edit_message_id")
    chat_id = message.chat.id
    email = data["email"]
    password = message.text.strip()

    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except Exception:
        pass

    try:
        token = await api_client.login(email=email, password=password)
    except Exception as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Назад в главное меню", callback_data="back_to_main")]
        ])
        text = f"❌ Ошибка входа: {e}"
        bot = get_bot()
        if edit_message_id:
            try:
                await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
            except Exception:
                pass
        await state.clear()
        return

    SESSIONS[chat_id] = UserSession(access_token=token, email=email)
    text, keyboard = _get_main_menu(chat_id)
    text = "✅ Вы успешно авторизованы! Теперь можете управлять задачами.\n\n" + text
    bot = get_bot()
    if edit_message_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
        except Exception:
            pass
    await state.clear()


@router.message(Command("logout"))
async def cmd_logout(message: Message) -> None:
    chat_id = message.chat.id
    if chat_id in SESSIONS:
        del SESSIONS[chat_id]
        await message.answer("Вы вышли из аккаунта.")
    else:
        await message.answer("Вы не авторизованы.")


# ---------- Смена пароля ----------


@router.message(Command("change_password"))
async def cmd_change_password(message: Message, state: FSMContext) -> None:
    session = await _require_session(message)
    if not session:
        return
    await state.set_state(ChangePasswordStates.old_password)
    await message.answer("Введите старый пароль:")


@router.message(ChangePasswordStates.old_password)
async def change_password_old(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    edit_message_id = data.get("edit_message_id")
    chat_id = message.chat.id
    
    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except Exception:
        pass
    
    await state.update_data(old_password=message.text.strip())
    await state.set_state(ChangePasswordStates.new_password)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Назад", callback_data="settings")]
    ])
    text = "Введите новый пароль (минимум 6 символов):"
    
    bot = get_bot()
    if edit_message_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
        except Exception:
            pass


@router.message(ChangePasswordStates.new_password)
async def change_password_new(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    old_password = data["old_password"]
    new_password = message.text.strip()
    edit_message_id = data.get("edit_message_id")
    chat_id = message.chat.id

    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except Exception:
        pass

    session = SESSIONS.get(chat_id)
    if not session:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Назад в главное меню", callback_data="back_to_main")]
        ])
        text = "❌ Вы не авторизованы. Воспользуйтесь входом."
        bot = get_bot()
        if edit_message_id:
            try:
                await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
            except Exception:
                pass
        await state.clear()
        return
    
    if len(new_password) < 6:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Назад в настройки", callback_data="settings")]
        ])
        text = "❌ Новый пароль должен содержать минимум 6 символов."
        bot = get_bot()
        if edit_message_id:
            try:
                await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
            except Exception:
                pass
        await state.clear()
        return

    try:
        await api_client.change_password(
            token=session.access_token,
            old_password=old_password,
            new_password=new_password,
        )
    except httpx.HTTPStatusError as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Назад в настройки", callback_data="settings")]
        ])
        if e.response.status_code in (400, 401) or "неверный" in str(e).lower() or "invalid" in str(e).lower():
            text = "❌ Неверный старый пароль."
        else:
            text = f"❌ Ошибка смены пароля: {e}"
        bot = get_bot()
        if edit_message_id:
            try:
                await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
            except Exception:
                pass
        await state.clear()
        return
    except Exception as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Назад в главное меню", callback_data="back_to_main")]
        ])
        text = f"❌ Ошибка: {e}"
        bot = get_bot()
        if edit_message_id:
            try:
                await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
            except Exception:
                pass
        await state.clear()
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Назад в настройки", callback_data="settings")]
    ])
    text = "✅ Пароль успешно изменён."
    bot = get_bot()
    if edit_message_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
        except Exception:
            pass
    await state.clear()


@router.message(Command("me"))
async def cmd_me(message: Message) -> None:
    session = await _require_session(message)
    if not session:
        return
    try:
        user = await api_client.get_me(token=session.access_token)
    except Exception as e:
        await message.answer(f"Не удалось получить информацию о пользователе: {e}")
        return
    text = (
        "Текущий пользователь:\n"
        f"ID: {user.get('id')}\n"
        f"Никнейм: {user.get('nickname')}\n"
        f"Email: {user.get('email')}\n"
        f"Роль: {user.get('role')}"
    )
    await message.answer(text)


# ---------- Список задач ----------


@router.message(Command("tasks"))
async def cmd_tasks(message: Message) -> None:
    await _show_tasks_with_filter(message, show_completed=True)


async def _show_tasks_with_filter(message_or_query: Message | CallbackQuery, show_completed: bool = True) -> None:
    """Показывает задачи с фильтром по статусу и inline кнопками."""
    if isinstance(message_or_query, CallbackQuery):
        chat_id = message_or_query.message.chat.id
        session = SESSIONS.get(chat_id)
        if not session:
            await message_or_query.answer("Вы не авторизованы. Используйте /login", show_alert=True)
            return
        message = message_or_query.message
    else:
        chat_id = message_or_query.chat.id
        session = SESSIONS.get(chat_id)
        if not session:
            await message_or_query.answer(
                "Вы не авторизованы. Воспользуйтесь командами /register или /login."
            )
            return
        message = message_or_query

    try:
        all_tasks = await api_client.list_tasks(token=session.access_token)
    except Exception as e:
        if isinstance(message_or_query, CallbackQuery):
            await message_or_query.answer(f"Ошибка: {e}", show_alert=True)
        else:
            await message.answer(f"Не удалось получить список задач: {e}")
        return

    # Фильтруем задачи по статусу
    if show_completed:
        tasks = all_tasks
        filter_text = "все задачи"
    else:
        tasks = [t for t in all_tasks if not t.get("completed", False)]
        filter_text = "невыполненные задачи"

    if not tasks:
        text = f"У вас нет {filter_text}." if not show_completed else "У вас пока нет задач."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать задачу", callback_data="newtask")],
            [
                InlineKeyboardButton(text="📋 Все задачи", callback_data="tasks_all"),
                InlineKeyboardButton(text="⏳ Невыполненные", callback_data="tasks_pending")
            ],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_main")]
        ])
        if isinstance(message_or_query, CallbackQuery):
            try:
                await message_or_query.message.edit_text(text, reply_markup=keyboard)
            except Exception:
                pass
            await message_or_query.answer()
        else:
            await message.answer(text, reply_markup=keyboard)
        return

    # Сортируем задачи по дате (ближайшие сначала)
    def get_deadline_sort_key(task):
        deadline = task.get('deadline_at')
        if not deadline:
            return datetime.max  # Задачи без дедлайна в конец
        try:
            return datetime.fromisoformat(deadline)
        except:
            return datetime.max
    
    sorted_tasks = sorted(tasks, key=get_deadline_sort_key)
    
    # Формируем список задач с кнопками для выбора
    text = f"Ваши {filter_text}:\n\nВыберите задачу для просмотра:"
    
    # Создаём кнопки с названиями задач
    task_buttons = []
    for task in sorted_tasks:
        task_id = task.get('id')
        title = task.get('title', 'Без названия')
        status = "✅" if task.get('completed') else "⏳"
        
        # Добавляем дату в кнопку
        raw_deadline = task.get('deadline_at')
        if raw_deadline:
            try:
                dt_utc = datetime.fromisoformat(raw_deadline)
                dt_local = _utc_to_local(chat_id, dt_utc)
                date_str = dt_local.strftime("%d.%m")
            except:
                date_str = ""
        else:
            date_str = "∞"
        
        # Ограничиваем длину названия для кнопки
        max_title_len = 30
        title_short = f"{title[:max_title_len]}..." if len(title) > max_title_len else title
        button_text = f"{status} {date_str} | {title_short}"
        task_buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"taskview_{task_id}")])
    
    # Добавляем кнопки навигации
    nav_buttons = [
        [
            InlineKeyboardButton(text="📋 Все" if not show_completed else "📋 Все ✓", callback_data="tasks_all"),
            InlineKeyboardButton(text="⏳ Невыполненные" if show_completed else "⏳ Невыполненные ✓", callback_data="tasks_pending")
        ],
        [InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_main")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=task_buttons + nav_buttons)

    if isinstance(message_or_query, CallbackQuery):
        try:
            await message_or_query.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            # Игнорируем ошибку "message is not modified" если контент не изменился
            pass
        await message_or_query.answer()
    else:
        await message.answer(text, reply_markup=keyboard)


@router.message(Command("today"))
async def cmd_today(message: Message) -> None:
    session = await _require_session(message)
    if not session:
        return

    try:
        tasks = await api_client.tasks_today(token=session.access_token)
    except Exception as e:
        await message.answer(f"Не удалось получить задачи на сегодня: {e}")
        return

    if not tasks:
        await message.answer("На сегодня задач нет.")
        return

    text = "Задачи на сегодня:\n\n" + "\n".join(_format_task(t, message.chat.id) for t in tasks)
    await message.answer(text)


@router.message(Command("search"))
async def cmd_search(message: Message) -> None:
    session = await _require_session(message)
    if not session:
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /search <текст для поиска>")
        return

    query = parts[1].strip()
    try:
        tasks = await api_client.search_tasks(token=session.access_token, query=query)
    except Exception as e:
        await message.answer(f"Ошибка поиска: {e}")
        return

    if not tasks:
        await message.answer("Ничего не найдено.")
        return

    text = "Результаты поиска:\n\n" + "\n".join(_format_task(t, message.chat.id) for t in tasks)
    await message.answer(text)


# ---------- Создание задачи ----------


@router.message(Command("newtask"))
async def cmd_new_task(message: Message, state: FSMContext) -> None:
    session = await _require_session(message)
    if not session:
        return

    await state.set_state(NewTaskStates.title)
    msg = await message.answer("Введите название задачи:")
    await state.update_data(edit_message_id=msg.message_id, chat_id=message.chat.id)


@router.message(NewTaskStates.title)
async def new_task_title(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    edit_message_id = data.get("edit_message_id")
    chat_id = message.chat.id
    
    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except Exception:
        pass
    
    await state.update_data(title=message.text.strip())
    await state.set_state(NewTaskStates.description)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_main")]
    ])
    text = "Введите описание задачи (или '-' если без описания):"
    
    bot = get_bot()
    if edit_message_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
        except Exception:
            pass


@router.message(NewTaskStates.description)
async def new_task_description(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    edit_message_id = data.get("edit_message_id")
    chat_id = message.chat.id
    
    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except Exception:
        pass
    
    desc = message.text.strip()
    if desc == "-":
        desc = None
    await state.update_data(description=desc)
    await state.set_state(NewTaskStates.is_important)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_main")]
    ])
    text = "Задача важная? (да/нет):"
    
    bot = get_bot()
    if edit_message_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
        except Exception:
            pass


@router.message(NewTaskStates.is_important)
async def new_task_is_important(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    edit_message_id = data.get("edit_message_id")
    chat_id = message.chat.id
    
    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except Exception:
        pass
    
    answer = message.text.strip().lower()
    is_important = answer in ("да", "yes", "y", "д")
    await state.update_data(is_important=is_important)
    await state.set_state(NewTaskStates.deadline)
    offset = _get_utc_offset_hours(chat_id)
    sign = "+" if offset >= 0 else ""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_main")]
    ])
    text = (
        "Введите дедлайн в формате ГГГГ-ММ-ДД ЧЧ:ММ "
        f"(в вашем местном времени, сейчас установлен часовой пояс UTC{sign}{offset})\n"
        "или '-' если без дедлайна:"
    )
    
    bot = get_bot()
    if edit_message_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
        except Exception:
            pass


@router.message(NewTaskStates.deadline)
async def new_task_deadline(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    edit_message_id = data.get("edit_message_id")
    chat_id = message.chat.id
    session = SESSIONS.get(chat_id)
    
    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except Exception:
        pass
    
    if not session:
        await state.clear()
        return

    text_input = message.text.strip()
    deadline_iso: Optional[str]
    if text_input == "-":
        deadline_iso = None
    else:
        try:
            # ожидаем формат "YYYY-MM-DD HH:MM" в ЛОКАЛЬНОМ времени пользователя
            dt_local = datetime.strptime(text_input, "%Y-%m-%d %H:%M")
            dt_utc = _local_to_utc(chat_id, dt_local)
            deadline_iso = dt_utc.isoformat()
        except ValueError:
            # Не переходим в следующее состояние - даём пользователю ввести дату заново
            offset = _get_utc_offset_hours(chat_id)
            sign = "+" if offset >= 0 else ""
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_main")]
            ])
            text = (
                "❌ Неверный формат даты. Используйте ГГГГ-ММ-ДД ЧЧ:ММ, например: 2025-12-31 18:30\n\n"
                f"(в вашем местном времени, сейчас установлен часовой пояс UTC{sign}{offset})\n"
                "или '-' если без дедлайна:"
            )
            bot = get_bot()
            if edit_message_id:
                try:
                    await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
                except Exception:
                    pass
            return

    try:
        task = await api_client.create_task(
            token=session.access_token,
            title=data["title"],
            description=data["description"],
            is_important=data["is_important"],
            deadline_at_iso=deadline_iso,
        )
    except Exception as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Назад в главное меню", callback_data="back_to_main")]
        ])
        text = f"❌ Не удалось создать задачу: {e}"
        bot = get_bot()
        if edit_message_id:
            try:
                await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
            except Exception:
                pass
        await state.clear()
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Назад в главное меню", callback_data="back_to_main")]
    ])
    text = "✅ Задача создана:\n\n" + _format_task(task, chat_id)
    bot = get_bot()
    if edit_message_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
        except Exception:
            pass
    await state.clear()


# ---------- Редактирование задачи (старая команда /edittask) ----------
# Теперь редактирование происходит через inline-кнопки (см. callback_edit_task)


# ---------- Завершение задачи ----------


@router.message(Command("complete"))
async def cmd_complete(message: Message) -> None:
    session = await _require_session(message)
    if not session:
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Использование: /complete <ID задачи>")
        return

    try:
        task_id = int(parts[1])
    except ValueError:
        await message.answer("ID задачи должен быть числом.")
        return

    try:
        task = await api_client.complete_task(
            token=session.access_token,
            task_id=task_id,
        )
    except Exception as e:
        await message.answer(f"Не удалось завершить задачу: {e}")
        return

    await message.answer("Задача отмечена как выполненная:\n\n" + _format_task(task, message.chat.id))


@router.message(Command("delete"))
async def cmd_delete(message: Message) -> None:
    session = await _require_session(message)
    if not session:
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Использование: /delete <ID задачи>")
        return

    try:
        task_id = int(parts[1])
    except ValueError:
        await message.answer("ID задачи должен быть числом.")
        return

    try:
        resp = await api_client.delete_task(token=session.access_token, task_id=task_id)
    except Exception as e:
        await message.answer(f"Не удалось удалить задачу: {e}")
        return

    title = resp.get("title") or ""
    await message.answer(f"Задача удалена. ID: {task_id} {('- ' + title) if title else ''}")


# ---------- Напоминания о дедлайнах ----------


async def reminders_worker(bot: Bot) -> None:
    """
    Периодически обходит авторизованных пользователей и напоминает
    о задачах с приближающимся дедлайном (0-1 дней до дедлайна).
    Напоминания отправляются не чаще одного раза в сутки для каждого пользователя.
    """
    while True:
        try:
            now = datetime.now(timezone.utc)
            
            for chat_id, session in list(SESSIONS.items()):
                # Проверяем, прошло ли 24 часа с последнего напоминания
                last_sent = LAST_REMINDER_SENT.get(chat_id)
                if last_sent:
                    time_since_last = now - last_sent
                    if time_since_last < timedelta(hours=24):
                        continue  # Ещё не прошло 24 часа, пропускаем
                
                try:
                    deadlines = await api_client.get_deadlines(token=session.access_token)
                except Exception:
                    # Если токен протух или backend недоступен — просто пропускаем
                    continue

                # Фильтруем задачи, у которых дедлайн сегодня или завтра
                important_tasks = [
                    t
                    for t in deadlines
                    if isinstance(t.get("days_left"), int)
                    and -1 <= t["days_left"] <= 1
                ]
                if not important_tasks:
                    continue

                text_lines = ["Напоминание о задачах с приближающимся дедлайном:"]
                for t in important_tasks:
                    title = t.get("title")
                    days_left = t.get("days_left")
                    text_lines.append(f"• {title} — осталось дней: {days_left}")

                await bot.send_message(chat_id=chat_id, text="\n".join(text_lines))
                # Сохраняем время отправки напоминания
                LAST_REMINDER_SENT[chat_id] = now
        except Exception:
            # Глобальная защита от падения цикла
            pass

        # Проверяем раз в 5 минут
        await asyncio.sleep(300)


# ---------- Callback обработчики ----------


@router.callback_query(F.data == "tasks_all")
async def callback_tasks_all(callback: CallbackQuery) -> None:
    await _show_tasks_with_filter(callback, show_completed=True)


@router.callback_query(F.data == "tasks_pending")
async def callback_tasks_pending(callback: CallbackQuery) -> None:
    await _show_tasks_with_filter(callback, show_completed=False)


@router.callback_query(F.data == "newtask")
async def callback_newtask(callback: CallbackQuery, state: FSMContext) -> None:
    chat_id = callback.message.chat.id
    session = SESSIONS.get(chat_id)
    if not session:
        await callback.answer("Вы не авторизованы. Используйте /login", show_alert=True)
        return
    
    await state.set_state(NewTaskStates.title)
    await state.update_data(edit_message_id=callback.message.message_id, chat_id=chat_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_main")]
    ])
    try:
        await callback.message.edit_text("Введите название задачи:", reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "today")
async def callback_today(callback: CallbackQuery) -> None:
    chat_id = callback.message.chat.id
    session = SESSIONS.get(chat_id)
    if not session:
        await callback.answer("Вы не авторизованы. Используйте /login", show_alert=True)
        text, keyboard = _get_main_menu(chat_id)
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            pass
        return

    try:
        tasks = await api_client.tasks_today(token=session.access_token)
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)
        text, keyboard = _get_main_menu(chat_id)
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            pass
        return

    if not tasks:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_main")]
        ])
        try:
            await callback.message.edit_text("На сегодня задач нет.", reply_markup=keyboard)
        except Exception:
            pass
        await callback.answer()
        return

    # Формируем список задач с кнопками для выбора
    text = "Задачи на сегодня:\n\nВыберите задачу для просмотра:"
    
    # Создаём кнопки с названиями задач
    task_buttons = []
    for task in tasks:
        task_id = task.get('id')
        title = task.get('title', 'Без названия')
        status = "✅" if task.get('completed') else "⏳"
        # Ограничиваем длину названия для кнопки
        button_text = f"{status} {title[:40]}..." if len(title) > 40 else f"{status} {title}"
        task_buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"taskview_{task_id}")])
    
    # Добавляем кнопку возврата
    nav_buttons = [[InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_main")]]
    keyboard = InlineKeyboardMarkup(inline_keyboard=task_buttons + nav_buttons)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "search_prompt")
async def callback_search_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    chat_id = callback.message.chat.id
    session = SESSIONS.get(chat_id)
    if not session:
        await callback.answer("Вы не авторизованы. Используйте /login", show_alert=True)
        text, keyboard = _get_main_menu(chat_id)
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            pass
        return
    
    await state.set_state(SearchStates.query)
    await state.update_data(edit_message_id=callback.message.message_id, chat_id=chat_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_main")]
    ])
    try:
        await callback.message.edit_text("Введите текст для поиска задач:", reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer()


@router.message(SearchStates.query)
async def search_query(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    edit_message_id = data.get("edit_message_id")
    chat_id = message.chat.id
    session = SESSIONS.get(chat_id)
    
    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except Exception:
        pass
    
    if not session:
        await state.clear()
        return
    
    query = message.text.strip()
    if not query:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_main")]
        ])
        text = "❌ Текст для поиска не может быть пустым."
        bot = get_bot()
        if edit_message_id:
            try:
                await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
            except Exception:
                pass
        await state.clear()
        return
    
    try:
        tasks = await api_client.search_tasks(token=session.access_token, query=query)
    except httpx.HTTPStatusError as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Назад в главное меню", callback_data="back_to_main")]
        ])
        if e.response.status_code == 404:
            text = "🔍 Таких задач нет."
        else:
            text = f"❌ Ошибка поиска: {e}"
        bot = get_bot()
        if edit_message_id:
            try:
                await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
            except Exception:
                pass
        await state.clear()
        return
    except Exception as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Назад в главное меню", callback_data="back_to_main")]
        ])
        text = f"❌ Ошибка поиска: {e}"
        bot = get_bot()
        if edit_message_id:
            try:
                await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
            except Exception:
                pass
        await state.clear()
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_main")]
    ])
    
    if not tasks:
        text = "🔍 Таких задач нет."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_main")]
        ])
    else:
        # Сортируем задачи по дате (ближайшие сначала)
        def get_deadline_sort_key(task):
            deadline = task.get('deadline_at')
            if not deadline:
                return datetime.max
            try:
                return datetime.fromisoformat(deadline)
            except:
                return datetime.max
        
        sorted_tasks = sorted(tasks, key=get_deadline_sort_key)
        
        # Формируем список задач с кнопками для выбора
        text = "🔍 Результаты поиска:\n\nВыберите задачу для просмотра:"
        
        # Создаём кнопки с названиями задач
        task_buttons = []
        for task in sorted_tasks:
            task_id = task.get('id')
            title = task.get('title', 'Без названия')
            status = "✅" if task.get('completed') else "⏳"
            
            # Добавляем дату в кнопку
            raw_deadline = task.get('deadline_at')
            if raw_deadline:
                try:
                    dt_utc = datetime.fromisoformat(raw_deadline)
                    dt_local = _utc_to_local(chat_id, dt_utc)
                    date_str = dt_local.strftime("%d.%m")
                except:
                    date_str = ""
            else:
                date_str = "∞"
            
            # Ограничиваем длину названия для кнопки
            max_title_len = 30
            title_short = f"{title[:max_title_len]}..." if len(title) > max_title_len else title
            button_text = f"{status} {date_str} | {title_short}"
            task_buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"taskview_{task_id}")])
        
        # Добавляем кнопку возврата
        nav_buttons = [[InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_main")]]
        keyboard = InlineKeyboardMarkup(inline_keyboard=task_buttons + nav_buttons)
    
    bot = get_bot()
    if edit_message_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
        except Exception:
            pass
    await state.clear()


@router.callback_query(F.data == "settings")
async def callback_settings(callback: CallbackQuery) -> None:
    await callback_settings_helper(get_bot(), callback.message.chat.id, callback.message.message_id)
    await callback.answer()


@router.callback_query(F.data == "me")
async def callback_me(callback: CallbackQuery) -> None:
    chat_id = callback.message.chat.id
    session = SESSIONS.get(chat_id)
    if not session:
        await callback.answer("Вы не авторизованы. Используйте /login", show_alert=True)
        return

    try:
        user_info = await api_client.get_me(token=session.access_token)
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)
        return

    text = (
        f"Информация о вас:\n\n"
        f"ID: {user_info.get('id')}\n"
        f"Никнейм: {user_info.get('nickname')}\n"
        f"Email: {user_info.get('email')}\n"
        f"Роль: {user_info.get('role')}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_main")]
    ])
    
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "back_to_main")
async def callback_back_to_main(callback: CallbackQuery) -> None:
    text, keyboard = _get_main_menu(callback.message.chat.id)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "register")
async def callback_register(callback: CallbackQuery, state: FSMContext) -> None:
    await _start_register(callback, state)


@router.callback_query(F.data == "login")
async def callback_login(callback: CallbackQuery, state: FSMContext) -> None:
    await _start_login(callback, state)




@router.callback_query(F.data == "timezone_settings")
async def callback_timezone_settings(callback: CallbackQuery, state: FSMContext) -> None:
    chat_id = callback.message.chat.id
    current_offset = _get_utc_offset_hours(chat_id)
    current_sign = "+" if current_offset >= 0 else ""
    
    await state.set_state(TimezoneStates.offset)
    await state.update_data(edit_message_id=callback.message.message_id, chat_id=chat_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Назад", callback_data="settings")]
    ])
    
    text = f"🌍 Введите часовой пояс (например: +3 или -5)\n\nТекущий: UTC{current_sign}{current_offset}"
    
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer()


@router.message(TimezoneStates.offset)
async def timezone_offset(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    edit_message_id = data.get("edit_message_id")
    chat_id = message.chat.id
    
    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except Exception:
        pass
    
    raw_offset = message.text.strip().replace("UTC", "").replace("utc", "").strip()
    try:
        offset = int(raw_offset)
    except ValueError:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Назад в настройки", callback_data="settings")]
        ])
        text = "❌ Неверный формат. Введите целое число часов (например: +3 или -5)"
        bot = get_bot()
        if edit_message_id:
            try:
                await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
            except Exception:
                pass
        await state.clear()
        return
    
    if not -12 <= offset <= 14:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Назад в настройки", callback_data="settings")]
        ])
        text = "❌ Часовой пояс должен быть в диапазоне от -12 до +14 часов."
        bot = get_bot()
        if edit_message_id:
            try:
                await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
            except Exception:
                pass
        await state.clear()
        return
    
    TIMEZONE_OFFSETS[chat_id] = offset
    sign = "+" if offset >= 0 else ""
    
    # Возвращаемся в настройки
    await callback_settings_helper(bot=get_bot(), chat_id=chat_id, message_id=edit_message_id)
    await state.clear()


async def callback_settings_helper(bot: Bot, chat_id: int, message_id: int) -> None:
    """Helper для показа настроек."""
    offset = _get_utc_offset_hours(chat_id)
    sign = "+" if offset >= 0 else ""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🌍 Часовой пояс: UTC{sign}{offset}", callback_data="timezone_settings")],
        [InlineKeyboardButton(text="🔑 Сменить пароль", callback_data="change_password")],
        [InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_main")]
    ])
    
    text = "⚙️ Настройки"
    try:
        await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=keyboard)
    except Exception:
        pass


@router.callback_query(F.data == "change_password")
async def callback_change_password(callback: CallbackQuery, state: FSMContext) -> None:
    chat_id = callback.message.chat.id
    session = SESSIONS.get(chat_id)
    if not session:
        await callback.answer("Вы не авторизованы. Используйте /login", show_alert=True)
        text, keyboard = _get_main_menu(chat_id)
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            pass
        return
    
    await state.set_state(ChangePasswordStates.old_password)
    await state.update_data(edit_message_id=callback.message.message_id, chat_id=chat_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Назад", callback_data="settings")]
    ])
    try:
        await callback.message.edit_text("Введите старый пароль:", reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("taskview_"))
async def callback_task_view(callback: CallbackQuery) -> None:
    """Показывает детальную информацию о задаче с кнопками действий."""
    chat_id = callback.message.chat.id
    session = SESSIONS.get(chat_id)
    if not session:
        await callback.answer("Вы не авторизованы. Используйте /login", show_alert=True)
        return
    
    try:
        task_id = int(callback.data.replace("taskview_", ""))
    except ValueError:
        await callback.answer("Ошибка: неверный ID задачи", show_alert=True)
        return
    
    # Получаем информацию о задаче
    try:
        all_tasks = await api_client.list_tasks(token=session.access_token)
        task = next((t for t in all_tasks if t.get('id') == task_id), None)
        if not task:
            await callback.answer("Задача не найдена", show_alert=True)
            return
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)
        return
    
    # Формируем текст с информацией о задаче
    text = "📋 Информация о задаче:\n\n" + _format_task(task, chat_id)
    
    # Создаём кнопки действий
    buttons = []
    if not task.get('completed'):
        buttons.append([InlineKeyboardButton(text="✅ Выполнить", callback_data=f"complete_{task_id}")])
    buttons.append([InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_{task_id}")])
    buttons.append([InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_{task_id}")])
    buttons.append([InlineKeyboardButton(text="↩️ Назад к списку", callback_data="tasks_all")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("delete_"))
async def callback_delete_task(callback: CallbackQuery) -> None:
    """Обработчик удаления задачи через inline-кнопку."""
    chat_id = callback.message.chat.id
    session = SESSIONS.get(chat_id)
    if not session:
        await callback.answer("Вы не авторизованы. Используйте /login", show_alert=True)
        return
    
    try:
        task_id = int(callback.data.replace("delete_", ""))
    except ValueError:
        await callback.answer("Ошибка: неверный ID задачи", show_alert=True)
        return
    
    try:
        result = await api_client.delete_task(token=session.access_token, task_id=task_id)
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)
        return
    
    title = result.get("title", "")
    text = f"🗑️ Задача удалена\n\nID: {task_id}\nНазвание: {title}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Назад к задачам", callback_data="tasks_all")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer("Задача удалена")


@router.callback_query(F.data.startswith("complete_"))
async def callback_complete_task(callback: CallbackQuery) -> None:
    """Обработчик выполнения задачи через inline-кнопку."""
    chat_id = callback.message.chat.id
    session = SESSIONS.get(chat_id)
    if not session:
        await callback.answer("Вы не авторизованы. Используйте /login", show_alert=True)
        return
    
    try:
        task_id = int(callback.data.replace("complete_", ""))
    except ValueError:
        await callback.answer("Ошибка: неверный ID задачи", show_alert=True)
        return
    
    try:
        task = await api_client.complete_task(token=session.access_token, task_id=task_id)
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)
        return
    
    text = "✅ Задача выполнена:\n\n" + _format_task(task, chat_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Назад в меню", callback_data="back_to_main")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer("Задача выполнена!")


@router.callback_query(F.data.startswith("edit_"))
async def callback_edit_task(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик редактирования задачи через inline-кнопку."""
    chat_id = callback.message.chat.id
    session = SESSIONS.get(chat_id)
    if not session:
        await callback.answer("Вы не авторизованы. Используйте /login", show_alert=True)
        return
    
    try:
        task_id = int(callback.data.replace("edit_", ""))
    except ValueError:
        await callback.answer("Ошибка: неверный ID задачи", show_alert=True)
        return
    
    await state.set_state(EditTaskStates.field)
    await state.update_data(task_id=task_id, edit_message_id=callback.message.message_id, chat_id=chat_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Название", callback_data="editfield_title")],
        [InlineKeyboardButton(text="📄 Описание", callback_data="editfield_description")],
        [InlineKeyboardButton(text="⚠️ Важность", callback_data="editfield_importance")],
        [InlineKeyboardButton(text="📅 Дедлайн", callback_data="editfield_deadline")],
        [InlineKeyboardButton(text="↩️ Назад к задаче", callback_data=f"taskview_{task_id}")]
    ])
    text = f"Редактирование задачи #{task_id}\n\nВыберите поле для редактирования:"
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("editfield_"))
async def callback_edit_field(callback: CallbackQuery, state: FSMContext) -> None:
    """Выбор поля для редактирования."""
    field = callback.data.replace("editfield_", "")
    data = await state.get_data()
    task_id = data.get("task_id")
    edit_message_id = data.get("edit_message_id")
    chat_id = callback.message.chat.id
    
    await state.update_data(field=field)
    await state.set_state(EditTaskStates.value)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Назад", callback_data=f"edit_{task_id}")]
    ])
    
    if field == "title":
        text = "Введите новое название задачи:"
    elif field == "description":
        text = "Введите новое описание задачи (или '-' для удаления):"
    elif field == "importance":
        text = "Задача важная? (да/нет):"
    elif field == "deadline":
        offset = _get_utc_offset_hours(chat_id)
        sign = "+" if offset >= 0 else ""
        text = (
            f"Введите новый дедлайн в формате ГГГГ-ММ-ДД ЧЧ:ММ\n"
            f"(в вашем местном времени UTC{sign}{offset})\n"
            "или '-' для удаления:"
        )
    else:
        text = "Введите новое значение:"
    
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer()


@router.message(EditTaskStates.value)
async def edit_task_value(message: Message, state: FSMContext) -> None:
    """Обработка нового значения поля задачи."""
    data = await state.get_data()
    task_id = data.get("task_id")
    field = data.get("field")
    edit_message_id = data.get("edit_message_id")
    chat_id = message.chat.id
    session = SESSIONS.get(chat_id)
    
    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except Exception:
        pass
    
    if not session:
        await state.clear()
        return
    
    value = message.text.strip()
    
    # Подготовка параметров для обновления
    update_params = {}
    
    if field == "title":
        update_params["title"] = value
    elif field == "description":
        update_params["description"] = None if value == "-" else value
    elif field == "importance":
        is_important = value.lower() in ("да", "yes", "y", "д")
        update_params["is_important"] = is_important
    elif field == "deadline":
        if value == "-":
            update_params["deadline_at_iso"] = None
        else:
            try:
                dt_local = datetime.strptime(value, "%Y-%m-%d %H:%M")
                dt_utc = _local_to_utc(chat_id, dt_local)
                update_params["deadline_at_iso"] = dt_utc.isoformat()
            except ValueError:
                offset = _get_utc_offset_hours(chat_id)
                sign = "+" if offset >= 0 else ""
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="↩️ Назад", callback_data=f"edit_{task_id}")]
                ])
                text = (
                    "❌ Неверный формат даты. Используйте ГГГГ-ММ-ДД ЧЧ:ММ\n"
                    f"(в вашем местном времени UTC{sign}{offset})\n"
                    "или '-' для удаления:"
                )
                bot = get_bot()
                if edit_message_id:
                    try:
                        await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
                    except Exception:
                        pass
                return
    
    # Обновляем задачу
    try:
        task = await api_client.update_task(token=session.access_token, task_id=task_id, **update_params)
    except Exception as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Назад в главное меню", callback_data="back_to_main")]
        ])
        text = f"❌ Ошибка обновления задачи: {e}"
        bot = get_bot()
        if edit_message_id:
            try:
                await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
            except Exception:
                pass
        await state.clear()
        return
    
    # Показываем обновлённую задачу с кнопками
    text = "✅ Задача обновлена:\n\n" + _format_task(task, chat_id)
    
    # Создаём кнопки действий
    buttons = []
    if not task.get('completed'):
        buttons.append([InlineKeyboardButton(text="✅ Выполнить", callback_data=f"complete_{task_id}")])
    buttons.append([InlineKeyboardButton(text="✏️ Редактировать ещё", callback_data=f"edit_{task_id}")])
    buttons.append([InlineKeyboardButton(text="↩️ Назад к задачам", callback_data="tasks_all")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    bot = get_bot()
    if edit_message_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=keyboard)
        except Exception:
            pass
    await state.clear()


async def main() -> None:
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    set_bot(bot)  # Устанавливаем глобальный экземпляр бота
    dp = Dispatcher()
    dp.include_router(router)

    # Запускаем фоновый воркер напоминаний
    asyncio.create_task(reminders_worker(bot))

    try:
        await dp.start_polling(bot)
    finally:
        await api_client.close()


if __name__ == "__main__":
    asyncio.run(main())


