import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
import re

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

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
    title = State()
    description = State()
    deadline = State()


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
        f"Дедлайн (локальное время): {deadline_str}\n"
    )


async def _require_session(message: Message) -> Optional[UserSession]:
    chat_id = message.chat.id
    session = SESSIONS.get(chat_id)
    if not session:
        await message.answer(
            "Вы не авторизованы. Воспользуйтесь командами /register или /login."
        )
        return None
    return session


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Я бот для управления задачами.\n\n"
        "Доступные команды:\n"
        "/help - помощь\n"
        "/register - регистрация\n"
        "/login - вход\n"
        "/logout - выйти\n"
        "/timezone <сдвиг> - установить часовой пояс (например, /timezone +3)\n"
        "/change_password - смена пароля\n"
        "/me - информация о текущем пользователе\n"
        "/tasks - список задач\n"
        "/today - задачи на сегодня\n"
        "/search <текст> - поиск задач\n"
        "/newtask - создать задачу\n"
        "/edittask - изменить задачу\n"
        "/complete <id> - завершить задачу\n"
        "/delete <id> - удалить задачу\n"
    )


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


@router.message(Command("register"))
async def cmd_register(message: Message, state: FSMContext) -> None:
    await state.set_state(RegisterStates.nickname)
    await message.answer("Введите ваш никнейм:")


@router.message(RegisterStates.nickname)
async def register_nickname(message: Message, state: FSMContext) -> None:
    await state.update_data(nickname=message.text.strip())
    await state.set_state(RegisterStates.email)
    await message.answer("Введите ваш email:")


@router.message(RegisterStates.email)
async def register_email(message: Message, state: FSMContext) -> None:
    email = message.text.strip()
    # Простая валидация email, чтобы не слать заведомо неверные данные на backend
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        await message.answer("Некорректный email. Введите адрес в формате name@example.com:")
        return

    await state.update_data(email=email)
    await state.set_state(RegisterStates.password)
    await message.answer("Введите пароль (минимум 6 символов):")


@router.message(RegisterStates.password)
async def register_password(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    nickname = data["nickname"]
    email = data["email"]
    password = message.text.strip()

    try:
        await api_client.register_user(nickname=nickname, email=email, password=password)
    except Exception as e:  # httpx.HTTPError
        await message.answer(f"Ошибка регистрации: {e}")
        await state.clear()
        return

    await message.answer("Регистрация прошла успешно! Теперь выполните /login для входа.")
    await state.clear()


# ---------- Логин ----------


@router.message(Command("login"))
async def cmd_login(message: Message, state: FSMContext) -> None:
    await state.set_state(LoginStates.email)
    await message.answer("Введите email:")


@router.message(LoginStates.email)
async def login_email(message: Message, state: FSMContext) -> None:
    await state.update_data(email=message.text.strip())
    await state.set_state(LoginStates.password)
    await message.answer("Введите пароль:")


@router.message(LoginStates.password)
async def login_password(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    email = data["email"]
    password = message.text.strip()

    try:
        token = await api_client.login(email=email, password=password)
    except Exception as e:
        await message.answer(f"Ошибка входа: {e}")
        await state.clear()
        return

    SESSIONS[message.chat.id] = UserSession(access_token=token, email=email)
    await message.answer("Вы успешно авторизованы! Теперь можете управлять задачами.")
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
    await state.update_data(old_password=message.text.strip())
    await state.set_state(ChangePasswordStates.new_password)
    await message.answer("Введите новый пароль:")


@router.message(ChangePasswordStates.new_password)
async def change_password_new(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    old_password = data["old_password"]
    new_password = message.text.strip()

    session = await _require_session(message)
    if not session:
        await state.clear()
        return

    try:
        await api_client.change_password(
            token=session.access_token,
            old_password=old_password,
            new_password=new_password,
        )
    except Exception as e:
        await message.answer(f"Ошибка смены пароля: {e}")
        await state.clear()
        return

    await message.answer("Пароль успешно изменён.")
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
    session = await _require_session(message)
    if not session:
        return

    try:
        tasks = await api_client.list_tasks(token=session.access_token)
    except Exception as e:
        await message.answer(f"Не удалось получить список задач: {e}")
        return

    if not tasks:
        await message.answer("У вас пока нет задач.")
        return

    text = "Ваши задачи:\n\n" + "\n".join(_format_task(t, message.chat.id) for t in tasks)
    await message.answer(text)


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
    await message.answer("Введите название задачи:")


@router.message(NewTaskStates.title)
async def new_task_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text.strip())
    await state.set_state(NewTaskStates.description)
    await message.answer("Введите описание задачи (или '-' если без описания):")


@router.message(NewTaskStates.description)
async def new_task_description(message: Message, state: FSMContext) -> None:
    desc = message.text.strip()
    if desc == "-":
        desc = None
    await state.update_data(description=desc)
    await state.set_state(NewTaskStates.is_important)
    await message.answer("Задача важная? (да/нет):")


@router.message(NewTaskStates.is_important)
async def new_task_is_important(message: Message, state: FSMContext) -> None:
    answer = message.text.strip().lower()
    is_important = answer in ("да", "yes", "y", "д")
    await state.update_data(is_important=is_important)
    await state.set_state(NewTaskStates.deadline)
    offset = _get_utc_offset_hours(message.chat.id)
    sign = "+" if offset >= 0 else ""
    await message.answer(
        "Введите дедлайн в формате ГГГГ-ММ-ДД ЧЧ:ММ "
        f"(в вашем местном времени, сейчас установлен часовой пояс UTC{sign}{offset})\n"
        "или '-' если без дедлайна:"
    )


@router.message(NewTaskStates.deadline)
async def new_task_deadline(message: Message, state: FSMContext) -> None:
    session = await _require_session(message)
    if not session:
        await state.clear()
        return

    text = message.text.strip()
    deadline_iso: Optional[str]
    if text == "-":
        deadline_iso = None
    else:
        try:
            # ожидаем формат "YYYY-MM-DD HH:MM" в ЛОКАЛЬНОМ времени пользователя
            dt_local = datetime.strptime(text, "%Y-%m-%d %H:%M")
            dt_utc = _local_to_utc(message.chat.id, dt_local)
            deadline_iso = dt_utc.isoformat()
        except ValueError:
            await message.answer(
                "Неверный формат даты. Используйте ГГГГ-ММ-ДД ЧЧ:ММ, например: 2025-12-31 18:30"
            )
            return

    data = await state.get_data()
    try:
        task = await api_client.create_task(
            token=session.access_token,
            title=data["title"],
            description=data["description"],
            is_important=data["is_important"],
            deadline_at_iso=deadline_iso,
        )
    except Exception as e:
        await message.answer(f"Не удалось создать задачу: {e}")
        await state.clear()
        return

    await message.answer("Задача создана:\n\n" + _format_task(task, message.chat.id))
    await state.clear()


# ---------- Редактирование задачи ----------


@router.message(Command("edittask"))
async def cmd_edit_task(message: Message, state: FSMContext) -> None:
    session = await _require_session(message)
    if not session:
        return

    await state.set_state(EditTaskStates.task_id)
    await message.answer("Введите ID задачи, которую хотите изменить:")


@router.message(EditTaskStates.task_id)
async def edit_task_id(message: Message, state: FSMContext) -> None:
    try:
        task_id = int(message.text.strip())
    except ValueError:
        await message.answer("ID задачи должен быть числом. Попробуйте ещё раз.")
        return

    await state.update_data(task_id=task_id)
    await state.set_state(EditTaskStates.title)
    await message.answer(
        "Введите новое название (или '-' чтобы оставить без изменений):"
    )


@router.message(EditTaskStates.title)
async def edit_task_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip()
    if title == "-":
        title = None
    await state.update_data(title=title)
    await state.set_state(EditTaskStates.description)
    await message.answer(
        "Введите новое описание (или '-' чтобы оставить без изменений):"
    )


@router.message(EditTaskStates.description)
async def edit_task_description(message: Message, state: FSMContext) -> None:
    desc = message.text.strip()
    if desc == "-":
        desc = None
    await state.update_data(description=desc)
    await state.set_state(EditTaskStates.deadline)
    offset = _get_utc_offset_hours(message.chat.id)
    sign = "+" if offset >= 0 else ""
    await message.answer(
        "Введите новый дедлайн в формате ГГГГ-ММ-ДД ЧЧ:ММ "
        f"(в вашем местном времени, сейчас установлен часовой пояс UTC{sign}{offset})\n"
        "или '-' чтобы оставить без изменений:"
    )


@router.message(EditTaskStates.deadline)
async def edit_task_deadline(message: Message, state: FSMContext) -> None:
    session = await _require_session(message)
    if not session:
        await state.clear()
        return

    text = message.text.strip()
    deadline_iso: Optional[str]
    if text == "-":
        deadline_iso = None
    else:
        try:
            dt_local = datetime.strptime(text, "%Y-%m-%d %H:%M")
            dt_utc = _local_to_utc(message.chat.id, dt_local)
            deadline_iso = dt_utc.isoformat()
        except ValueError:
            await message.answer(
                "Неверный формат даты. Используйте ГГГГ-ММ-ДД ЧЧ:ММ, например: 2025-12-31 18:30"
            )
            return

    data = await state.get_data()
    task_id = int(data["task_id"])
    title = data["title"]
    description = data["description"]

    try:
        task = await api_client.update_task(
            token=session.access_token,
            task_id=task_id,
            title=title,
            description=description,
            deadline_at_iso=deadline_iso,
        )
    except Exception as e:
        await message.answer(f"Не удалось обновить задачу: {e}")
        await state.clear()
        return

    await message.answer("Задача обновлена:\n\n" + _format_task(task, message.chat.id))
    await state.clear()


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


async def main() -> None:
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
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


