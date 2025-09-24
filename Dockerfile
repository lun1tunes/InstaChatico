FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей1
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости
COPY pyproject.toml ./

# Установка Poetry
RUN pip install poetry

# Устанавливаем зависимости
RUN poetry config virtualenvs.create false && \
    poetry install --only main --no-interaction --no-ansi

# Копируем исходный код
COPY . .

# Применяем миграции при запуске (опционально)
# CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]