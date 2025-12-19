-- Тип для роли пользователя (соответствует Enum UserRole в models.user)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'userrole') THEN
        CREATE TYPE userrole AS ENUM ('user', 'admin');
    END IF;
END$$;

-- Таблица пользователей (users) — соответствует модели User в models/user.py
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    nickname        VARCHAR(50) UNIQUE NOT NULL,
    email           VARCHAR(100) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role            userrole NOT NULL DEFAULT 'user'
);

CREATE INDEX IF NOT EXISTS idx_users_nickname ON users (nickname);
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

-- Таблица задач (tasks) — соответствует модели Task в models/tasks.py
CREATE TABLE IF NOT EXISTS tasks (
    id           SERIAL PRIMARY KEY,
    title        TEXT NOT NULL,
    description  TEXT,
    is_important BOOLEAN NOT NULL DEFAULT FALSE,
    is_urgent    BOOLEAN NOT NULL DEFAULT FALSE,
    quadrant     VARCHAR(2) NOT NULL, -- Q1, Q2, Q3, Q4
    completed    BOOLEAN NOT NULL DEFAULT FALSE,
    deadline_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    user_id      INTEGER,
    CONSTRAINT fk_tasks_user_id
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks (user_id);

-- Демонстрационные данные для задач (user_id оставлен NULL, чтобы не требовать наличия пользователя)
INSERT INTO tasks (title, description, is_important, is_urgent, quadrant, completed, deadline_at)
VALUES
(
    'Подготовить отчёт за месяц',
    'Собрать статистику и оформить презентацию для руководства',
    TRUE,
    TRUE,
    'Q1',
    FALSE,
    '2025-01-25 18:00:00+00'
),
(
    'Пройти курс по Docker',
    'Изучить основы контейнеризации и развертывания приложений',
    TRUE,
    FALSE,
    'Q2',
    FALSE,
    '2025-02-10 20:00:00+00'
),
(
    'Позвонить врачу',
    NULL,
    FALSE,
    TRUE,
    'Q3',
    FALSE,
    '2025-01-05 12:00:00+00'
),
(
    'Погулять в парке',
    'Немного расслабиться после работы',
    FALSE,
    FALSE,
    'Q4',
    FALSE,
    '2025-01-03 19:00:00+00'
),
(
    'Сдать проект по FastAPI',
    'Завершить разработку API и написать документацию',
    TRUE,
    TRUE,
    'Q1',
    FALSE,
    '2025-01-30 23:59:00+00'
),
(
    'Изучить SQLAlchemy',
    'Прочитать документацию и попробовать примеры',
    TRUE,
    FALSE,
    'Q2',
    FALSE,
    '2025-02-15 21:00:00+00'
),
(
    'Сходить на лекцию',
    NULL,
    FALSE,
    TRUE,
    'Q3',
    FALSE,
    '2025-01-08 10:00:00+00'
),
(
    'Посмотреть фильм',
    'Выбрать новый фильм и посмотреть вечером',
    FALSE,
    FALSE,
    'Q4',
    FALSE,
    '2025-01-04 21:00:00+00'
)
ON CONFLICT DO NOTHING;


