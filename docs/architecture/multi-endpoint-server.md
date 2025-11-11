# Архитектура сервера с несколькими endpoint'ами

## Обзор

Архитектура позволяет создать один HTTP сервер с несколькими независимыми MCP endpoint'ами, каждый из которых подключен к своей базе данных с уникальными правами доступа.

## Компоненты

### 1. Главный сервер (Main Server)

**Назначение:**
- Точка входа для всех запросов
- Управление жизненным циклом всех подчиненных серверов
- Предоставление общих endpoints (например, health check)

**Характеристики:**
- FastMCP сервер с кастомными tools для управления серверами
- Имеет собственные custom routes (например, `/health`)
- Использует Starlette для HTTP роутинга

**Endpoint:**
- `/mcp` - главный сервер (MCP endpoint)
- `/health` - health check endpoint

**Инструменты главного сервера:**
- `get_server_info` - получить информацию о главном сервере и всех подчиненных
- `get_sub_server_config` - получить конфигурацию подчиненного сервера
- `list_all_servers` - получить список всех серверов с их конфигурацией
- `calculate_stats` - вычислить статистику для списка чисел

### 2. Подчиненные серверы (Sub Servers)

**Назначение:**
- Независимые MCP серверы, каждый со своим набором tools
- Каждый сервер подключен к своей базе данных
- Каждый сервер имеет свой набор инструментов в зависимости от прав доступа

**Характеристики:**
- FastMCP сервер с tools из ToolManager
- Уникальная конфигурация базы данных для каждого сервера
- Уникальный набор инструментов в зависимости от `access_mode`

**Endpoints:**
- `/app1/mcp` - сервер для app1
- `/app2/mcp` - сервер для app2
- `/app3/mcp` - сервер для app3
- `/app4/mcp` - сервер для app4

## Архитектурная диаграмма

```
┌─────────────────────────────────────────────────────────────┐
│                    HTTP Server (Port 8000)                   │
│                    (Starlette Application)                   │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ Main Server  │   │  Sub Server  │   │  Sub Server  │
│  (FastMCP)   │   │  app1 (MCP)  │   │  app2 (MCP)  │
│              │   │              │   │              │
│ - /mcp       │   │ - /app1/mcp  │   │ - /app2/mcp  │
│ - /health    │   │              │   │              │
│              │   │ Tools:       │   │ Tools:       │
│ Tools:       │   │ - list_*     │   │ - list_*     │
│ - get_*      │   │ - execute_sql│   │ - execute_sql│
│ - calculate_*│   │ - ...        │   │ - ...        │
└──────────────┘   └──────┬───────┘   └──────┬───────┘
                          │                  │
                          ▼                  ▼
                    ┌──────────┐      ┌──────────┐
                    │   DB1    │      │   DB2    │
                    │ (user_ro)│      │ (user_rw)│
                    └──────────┘      └──────────┘
```

## Структура данных

### Конфигурация подчиненных серверов

```python
SUB_SERVERS_CONFIG = {
    "app1": DatabaseConfig(
        database_uri=SecretStr("postgresql://...@localhost:5432/db1"),
        access_mode="user_ro",  # Только базовые инструменты (4 шт)
        endpoint=True,  # Монтируется как отдельный endpoint /app1/mcp
    ),
    "app2": DatabaseConfig(
        database_uri=SecretStr("postgresql://...@localhost:5432/db2"),
        access_mode="user_rw",  # Базовые инструменты + запись (4 шт)
        endpoint=True,  # Монтируется как отдельный endpoint /app2/mcp
    ),
    "app3": DatabaseConfig(
        database_uri=SecretStr("postgresql://...@localhost:5432/db3"),
        access_mode="admin_ro",  # Все инструменты (9 шт)
        endpoint=True,  # Монтируется как отдельный endpoint /app3/mcp
    ),
    "app4": DatabaseConfig(
        database_uri=SecretStr("postgresql://...@localhost:5432/db4"),
        access_mode="admin_rw",  # Все инструменты + неограниченный execute_sql (9 шт)
        endpoint=True,  # Монтируется как отдельный endpoint /app4/mcp
    ),
}
```

**Параметр `endpoint`:**
- `True`: Сервер монтируется как отдельный HTTP endpoint по пути `/{server_name}/mcp`
- `False` (по умолчанию): Сервер монтируется в основной endpoint через FastMCP mount() (Server Composition)

**Префиксы инструментов:**
Префикс к именам инструментов добавляется автоматически на основе имени сервера. Это предотвращает конфликты имен, когда несколько MCP серверов подключены к одному агенту.

## Режимы доступа и наборы инструментов

### Префиксы к именам инструментов

К именам инструментов автоматически добавляется префикс на основе имени сервера из конфигурации. Это предотвращает конфликты имен, когда несколько MCP серверов подключены к одному агенту.

**Пример:**
- Сервер `app1` с инструментом `list_objects` → имя инструмента: `app1_list_objects`
- Сервер `app2` с инструментом `list_objects` → имя инструмента: `app2_list_objects`

### USER_RO / USER_RW (4 инструмента)

**Инструменты с префиксом:**
- `{prefix}_list_objects` - список объектов в схеме public
- `{prefix}_get_object_details` - детали объекта
- `{prefix}_explain_query` - план выполнения запроса
- `{prefix}_execute_sql` - выполнение SQL (read-only для USER_RO, read-write для USER_RW)

**Отключенные инструменты:**
- `list_schemas` - недоступен (только public схема)
- `analyze_workload_indexes` - недоступен
- `analyze_query_indexes` - недоступен
- `analyze_db_health` - недоступен
- `get_top_queries` - недоступен

### ADMIN_RO / ADMIN_RW (9 инструментов)

**Инструменты с префиксом:**
- Все базовые инструменты (4 шт) с префиксом
- `{prefix}_list_schemas` - список всех схем
- `{prefix}_analyze_workload_indexes` - анализ индексов по workload
- `{prefix}_analyze_query_indexes` - анализ индексов по запросам
- `{prefix}_analyze_db_health` - анализ здоровья БД
- `{prefix}_get_top_queries` - топ медленных запросов

**Разница ADMIN_RO vs ADMIN_RW:**
- ADMIN_RO: `{prefix}_execute_sql` ограничен (только SELECT)
- ADMIN_RW: `{prefix}_execute_sql` неограничен (DDL, DML, DCL разрешены)

## Жизненный цикл (Lifespan)

### Инициализация (Startup)

1. **Создание ToolManager для каждого подчиненного сервера**
   - Каждый ToolManager создается с уникальной конфигурацией БД
   - Каждый ToolManager имеет свой пул подключений

2. **Регистрация tools на FastMCP серверах**
   - Tools регистрируются через `tool_manager.register_tools(sub_mcp, prefix=app_name)`
   - Каждый tool автоматически получает префикс для идентификации БД
   - Для серверов с `endpoint=True` создаются отдельные FastMCP серверы
   - Для серверов с `endpoint=False` tools регистрируются в основном сервере

3. **Создание HTTP приложений**
   - Каждый FastMCP сервер преобразуется в Starlette приложение через `http_app(path="/mcp")`
   - Главный сервер также преобразуется в Starlette приложение

4. **Монтирование через Starlette Mount**
   - Серверы с `endpoint=True` монтируются как отдельные endpoints: `Mount(f"/{app_name}", app=sub_app)`
   - Серверы с `endpoint=False` монтируются в основной endpoint через FastMCP mount() (Server Composition)
   - Главный сервер монтируется на корневой путь: `Mount("/", app=main_app)`

5. **Инициализация подключений к БД**
   - Для каждого ToolManager устанавливается подключение к БД
   - Проверяется, что подключение установлено к правильной БД

### Завершение (Shutdown)

1. **Закрытие подключений к БД**
   - Каждый ToolManager закрывает свой пул подключений
   - Используется AsyncExitStack для корректного закрытия всех ресурсов

## Ключевые принципы

### 1. Изоляция серверов

Каждый подчиненный сервер полностью изолирован:
- Свой экземпляр ToolManager
- Свой пул подключений к БД
- Свой набор tools
- Свой HTTP endpoint

### 2. Использование Starlette Mount и FastMCP mount()

**Важно:** 
- FastMCP `mount()` - для Server Composition (серверы с `endpoint=False`, префиксы tools/resources/prompts в одном endpoint)
- Starlette `Mount` - для разных HTTP endpoints (серверы с `endpoint=True`, разные пути)

### 3. Управление жизненным циклом

Все компоненты управляются через единый `lifespan` контекстный менеджер:
- ToolManager'ы входят в контекст через `async with tool_manager`
- HTTP приложения входят в контекст через `async with app.lifespan(app)`
- Используется `AsyncExitStack` для корректного закрытия всех ресурсов

### 4. Безопасность

- Каждый сервер имеет свои права доступа через `access_mode`
- SafeSqlDriver ограничивает доступ к схемам и операциям в user режиме
- Доступ к `information_schema.schemata` блокируется в user режиме

## Пример использования

### Создание подчиненного сервера

```python
def create_sub_server(app_name: str, config: DatabaseConfig) -> tuple[FastMCP, ToolManager]:
    """Создать подчиненный сервер с tools из ToolManager."""
    sub_mcp = FastMCP(name=f"SubServer-{app_name}")
    tool_manager = ToolManager(config)
    tool_manager.register_tools(sub_mcp, prefix=app_name)
    return sub_mcp, tool_manager
```

### Создание главного сервера

```python
def create_main_server() -> Starlette:
    """Создать главный сервер с кастомными tools и монтированными подчиненными серверами."""
    main_mcp = FastMCP(name="MainServer")
    
    # Health check endpoint
    @main_mcp.custom_route("/health", methods=["GET"])
    async def health_check(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "healthy", "service": "main-server"})
    
    # Кастомные tools для главного сервера
    @main_mcp.tool
    def get_server_info() -> dict[str, Any]:
        """Получить информацию о главном сервере и всех подчиненных серверах."""
        return {
            "server": "MainServer",
            "status": "running",
            "sub_servers": list(SUB_SERVERS_CONFIG.keys()),
            "endpoints": {
                "main": "/mcp",
                "health": "/health",
                **{app_name: f"/{app_name}/mcp" for app_name in SUB_SERVERS_CONFIG},
            },
        }
    
    @main_mcp.tool
    def get_sub_server_config(app_name: str) -> dict[str, Any]:
        """Получить конфигурацию подчиненного сервера."""
        # ... реализация ...
    
    @main_mcp.tool
    def list_all_servers() -> list[dict[str, Any]]:
        """Получить список всех серверов (главный + подчиненные) с их конфигурацией."""
        # ... реализация ...
    
    @main_mcp.tool
    def calculate_stats(numbers: list[int]) -> dict[str, Any]:
        """Вычислить статистику для списка чисел."""
        # ... реализация ...
    
    # Создание подчиненных серверов
    tool_managers: dict[str, ToolManager] = {}
    sub_apps: list[tuple[str, Starlette]] = []
    
    for app_name, config in SUB_SERVERS_CONFIG.items():
        sub_mcp, tool_manager = create_sub_server(app_name, config)
        tool_managers[app_name] = tool_manager
        sub_app = sub_mcp.http_app(path="/mcp")
        sub_apps.append((app_name, sub_app))
    
    main_app = main_mcp.http_app(path="/mcp")
    
    # Объединенный lifespan
    @asynccontextmanager
    async def combined_lifespan(_app: Starlette) -> AsyncIterator[dict[str, Any]]:
        async with AsyncExitStack() as stack:
            # Вход в контекст ToolManager'ов
            for tool_manager in tool_managers.values():
                await stack.enter_async_context(tool_manager)
            
            # Инициализация подключений к БД
            for app_name, tool_manager in tool_managers.items():
                await tool_manager.db_connection.pool_connect()
            
            # Вход в контекст HTTP приложений
            for app_name, sub_app in sub_apps:
                if hasattr(sub_app, "lifespan") and sub_app.lifespan:
                    await stack.enter_async_context(sub_app.lifespan(_app))
            
            if hasattr(main_app, "lifespan") and main_app.lifespan:
                await stack.enter_async_context(main_app.lifespan(_app))
            
            yield {}
    
    # Монтирование через Starlette Mount
    routes = [
        Mount(f"/{app_name}", app=sub_app)
        for app_name, sub_app in sub_apps
    ]
    routes.append(Mount("/", app=main_app))
    
    return Starlette(routes=routes, lifespan=combined_lifespan)
```

### Запуск сервера

```python
async def run_server() -> None:
    """Запустить сервер."""
    app = create_main_server()
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
```

## Конфигурация MCP клиента

Для подключения к каждому серверу через MCP клиент (например, Cursor):

```json
{
  "mcpServers": {
    "main": {
      "url": "http://localhost:8000/mcp",
      "transport": "http"
    },
    "app1": {
      "url": "http://localhost:8000/app1/mcp",
      "transport": "http"
    },
    "app2": {
      "url": "http://localhost:8000/app2/mcp",
      "transport": "http"
    },
    "app3": {
      "url": "http://localhost:8000/app3/mcp",
      "transport": "http"
    },
    "app4": {
      "url": "http://localhost:8000/app4/mcp",
      "transport": "http"
    }
  }
}
```

**Примечание:** Главный сервер (`main`) предоставляет инструменты для управления и получения информации о всех серверах. Подчиненные серверы (`app1`, `app2`, `app3`, `app4`) предоставляют инструменты для работы с базами данных.

## Преимущества архитектуры

1. **Масштабируемость**: Легко добавить новые подчиненные серверы
2. **Изоляция**: Каждый сервер независим и изолирован
3. **Гибкость**: Разные права доступа для разных серверов
4. **Единая точка входа**: Один HTTP сервер для всех endpoint'ов
5. **Управление ресурсами**: Централизованное управление жизненным циклом

## Ограничения

1. **Один порт**: Все endpoint'ы работают на одном порту
2. **Один процесс**: Все серверы работают в одном процессе
3. **Общая конфигурация**: Некоторые настройки (например, timeout) общие для всех серверов

## Расширения

### Возможные улучшения:

1. **Динамическая конфигурация**: Загрузка конфигурации из файла или БД
2. **Мониторинг**: Добавление метрик и логирования для каждого сервера
3. **Аутентификация**: Добавление аутентификации для каждого endpoint'а
4. **Rate limiting**: Ограничение запросов для каждого сервера
5. **Health checks**: Индивидуальные health checks для каждого сервера

