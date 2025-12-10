from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import AsyncSessionLocal
from models import Task
from utils import calc_quadrant, is_urgent_from_deadline
from datetime import datetime


async def update_task_urgency():
    print(f"[{datetime.now()}] Запуск автоматического обновления срочности задач...")

    async with AsyncSessionLocal() as db:
        try:
            # Получаем все незавершенные задачи
            result = await db.execute(
                select(Task).where(Task.completed == False)
            )
            tasks = result.scalars().all()

            updated_count = 0

            for task in tasks:
                # Вычисляем новую срочность
                new_urgency = is_urgent_from_deadline(task.deadline_at)
                new_quadrant = calc_quadrant(task.is_important, task.deadline_at)

                # Обновляем, только если значения изменились
                if task.is_urgent != new_urgency or task.quadrant != new_quadrant:
                    task.is_urgent = new_urgency
                    task.quadrant = new_quadrant
                    updated_count += 1

            if updated_count > 0:
                await db.commit()
                print(f"Обновлено задач: {updated_count} из {len(tasks)}")
            else:
                print(f"Изменений не требуется. Проверено задач: {len(tasks)}")

        except Exception as e:
            print(f"Ошибка при обновлении срочности: {e}")
            await db.rollback()


def start_scheduler():
    """
    Запускает планировщик задач.
    """
    scheduler = AsyncIOScheduler()

    # Запускаем задачу каждый день в 09:00
    scheduler.add_job(
        update_task_urgency,
        trigger="cron",
        hour=9,
        minute=0,
        id="update_urgency",
        name="Обновление срочности задач",
        replace_existing=True,
    )

    #Для тестирования: запуск каждые 5 минут (закомментируйте после тестирования)
    scheduler.add_job(
        update_task_urgency,
        trigger="interval",
        minutes=1,
        id="update_urgency_test",
        name="Тестовое обновление срочности",
        replace_existing=True,
    )

    scheduler.start()
    print("Планировщик задач запущен")

    return scheduler
