FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей1
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Создаем пользователя для приложения с фиксированным UID/GID для совместимости с volume mounts
RUN groupadd -r -g 988 instagram-worker && useradd -r -u 988 -g instagram-worker instagram-worker

# Копируем зависимости
COPY pyproject.toml ./

# Установка Poetry
RUN pip install poetry

# Устанавливаем зависимости
RUN poetry config virtualenvs.create false && \
    poetry install --only main --no-interaction --no-ansi

# Копируем исходный код
COPY . .

# Создаем директорию для conversations и устанавливаем права
RUN mkdir -p /app/conversations && \
    chown -R instagram-worker:instagram-worker /app

# Переключаемся на пользователя instagram-worker
USER instagram-worker

# Применяем миграции при запуске (опционально)
# CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]