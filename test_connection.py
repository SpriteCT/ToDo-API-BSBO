import asyncio
from database import engine, init_db, Base
from models import Task
from sqlalchemy import text

async def test_connection():
    print(" Проверка подключения к PostgreSQL через Supabase...")
    try:
        # Пытаемся подключиться
        async with engine.begin() as conn:
        # Выполняем простой SQL запрос
            result = await conn.execute(text("SELECT 1"))
            print(" Подключение успешно!")
            print(f" Результат тестового запроса: {result.scalar()}")

        # Создаем таблицы (если их нет)
        print("\n Создание таблиц...")
        await init_db()

        print("\n ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!")
        print(" База данных готова к работе.")

    except Exception as e:
        print(f"\n ОШИБКА ПОДКЛЮЧЕНИЯ:")
        print(f" {e}")
        print("\nПроверьте:")
        print(" 1. Правильно ли указан DATABASE_URL в .env")
        print(" 2. Доступен ли интернет")
        print(" 3. Работает ли Supabase проект")

    finally:
        # Закрываем соединение
        await engine.dispose()
if __name__ == "__main__":
    asyncio.run(test_connection())