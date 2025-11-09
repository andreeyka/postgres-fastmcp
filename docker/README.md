# Тестовая среда Docker

Эта директория содержит конфигурацию для запуска тестовой среды с MCP сервером и PostgreSQL.

## Структура

- `docker-compose.yml` - основная конфигурация Docker Compose
- `postgres/init-db.sql` - скрипт инициализации PostgreSQL с тремя тестовыми базами данных
- `config.test.json` - тестовая конфигурация MCP сервера

## Тестовые базы данных

Создаются три тестовые базы данных:

1. **test_db1**
   - Пользователь: `test_user1`
   - Пароль: `test_pass1`

2. **test_db2**
   - Пользователь: `test_user2`
   - Пароль: `test_pass2`

3. **test_db3**
   - Пользователь: `test_user3`
   - Пароль: `test_pass3`

## Запуск

```bash
# Сборка и запуск всех сервисов
docker-compose up --build

# Запуск в фоновом режиме
docker-compose up -d --build

# Просмотр логов
docker-compose logs -f

# Остановка
docker-compose down

# Остановка с удалением volumes (удалит все данные БД)
docker-compose down -v
```

## Доступ

- **MCP сервер**: http://localhost:8000
- **PostgreSQL**: доступен только внутри Docker сети (порт 5432)

## Сеть

Все сервисы работают в изолированной Docker сети `mcp-network`. 
Наружу публикуется только порт 8000 для MCP сервера.
PostgreSQL доступен только внутри Docker сети по имени хоста `postgres`.
