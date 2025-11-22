# Многостадийная сборка для оптимизации размера образа

FROM repo.mng.sbercloud.tech/python:3.12-alpine3.19 AS python-base

# Стадия сборки
FROM python-base AS builder

# Устанавливаем uv
RUN pip install --no-cache-dir uv==0.9.7

# Устанавливаем системные зависимости для сборки
RUN apk add --no-cache \
  postgresql-dev \
  gcc \
  musl-dev \
  linux-headers

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы конфигурации проекта
# README.md нужен для сборки пакета (указан в pyproject.toml)
COPY pyproject.toml uv.lock README.md ./

# Копируем исходный код для сборки пакета
COPY src/ ./src/

# Синхронизируем зависимости (устанавливаем в виртуальное окружение)
RUN uv sync --no-dev

# Финальный образ
FROM python-base

# Устанавливаем системные зависимости для runtime
RUN apk add --no-cache \
  postgresql-libs \
  libpq

# Создаем пользователя для запуска приложения (безопасность)
RUN adduser -D -u 1000 appuser && \
  mkdir -p /app && \
  chown -R appuser:appuser /app

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем виртуальное окружение из builder
COPY --from=builder /app/.venv /app/.venv

# Копируем файлы проекта
COPY --chown=appuser:appuser pyproject.toml uv.lock ./
COPY --chown=appuser:appuser src/ ./src/

# Копируем .env файл (если он есть, будет скопирован; если нет - можно передать через docker run -e)
COPY --chown=appuser:appuser .env* ./

# Переключаемся на непривилегированного пользователя
USER appuser

# Устанавливаем PATH для использования виртуального окружения
ENV PATH="/app/.venv/bin:$PATH"

# Expose the HTTP port for MCP server
EXPOSE 8000

# Запускаем MCP сервер
# Используем установленный скрипт из pyproject.toml [project.scripts]
CMD ["postgres-fastmcp"]
