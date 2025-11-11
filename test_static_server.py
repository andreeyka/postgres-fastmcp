"""Тестовый код статического HTTP сервера с главным сервером и подчиненными.

Структура:
- Главный сервер без tools
- 4 подчиненных сервера с tools из ToolManager
- Подчиненные монтируются с путями /app1/mcp, /app2/mcp, /app3/mcp, /app4/mcp
- Каждый сервер подключается к своей БД

Важно:
- `mount()` в FastMCP используется для Server Composition (префиксы tools/resources/prompts)
- Для разных HTTP endpoints нужно использовать Starlette `Mount` для монтирования разных `http_app()`
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

import uvicorn
from fastmcp import FastMCP
from pydantic import SecretStr
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount

from postgres_mcp.config import DatabaseConfig

# Конфигурация для подчиненных серверов с подключением к БД
# Разные комбинации role и access_mode дают разные наборы инструментов:
# - user + restricted: только базовые инструменты (4 шт: list_objects, get_object_details, explain_query, execute_sql)
# - user + unrestricted: базовые инструменты + запись (4 шт)
# - full + restricted: все инструменты (9 шт: все базовые + admin инструменты)
# - full + unrestricted: все инструменты + неограниченный execute_sql (9 шт)
#
# Префикс к именам инструментов добавляется автоматически на основе имени сервера:
# - app1: app1_list_objects, app1_get_object_details, app1_execute_sql, app1_explain_query
# - app2: app2_list_objects, app2_get_object_details, app2_execute_sql, app2_explain_query
# - app3: app3_list_schemas, app3_list_objects, app3_execute_sql, ... (все 9 инструментов)
# - app4: app4_list_schemas, app4_list_objects, app4_execute_sql, ... (все 9 инструментов)
from postgres_mcp.enums import AccessMode, UserRole
from postgres_mcp.tool.tools import ToolManager


SUB_SERVERS_CONFIG = {
    "app1": DatabaseConfig(
        database_uri=SecretStr("postgresql://postgres:postgres@localhost:5432/db1"),
        role=UserRole.USER,
        access_mode=AccessMode.RESTRICTED,  # Только базовые инструменты (4 шт)
    ),
    "app2": DatabaseConfig(
        database_uri=SecretStr("postgresql://postgres:postgres@localhost:5432/db2"),
        role=UserRole.USER,
        access_mode=AccessMode.UNRESTRICTED,  # Базовые инструменты + запись (4 шт)
    ),
    "app3": DatabaseConfig(
        database_uri=SecretStr("postgresql://postgres:postgres@localhost:5432/db3"),
        role=UserRole.FULL,
        access_mode=AccessMode.RESTRICTED,  # Все инструменты (9 шт)
    ),
    "app4": DatabaseConfig(
        database_uri=SecretStr("postgresql://postgres:postgres@localhost:5432/db4"),
        role=UserRole.FULL,
        access_mode=AccessMode.UNRESTRICTED,  # Все инструменты + неограниченный execute_sql (9 шт)
    ),
}


def create_sub_server(app_name: str, config: DatabaseConfig) -> tuple[FastMCP, ToolManager]:
    """Создать подчиненный сервер с tools из ToolManager.

    Args:
        app_name: Имя приложения (app1, app2, и т.д.).
        config: Конфигурация базы данных.

    Returns:
        Кортеж из (FastMCP сервер, ToolManager).
    """
    sub_mcp = FastMCP(name=f"SubServer-{app_name}")

    # Создаем ToolManager для этого сервера с его уникальной конфигурацией
    tool_manager = ToolManager(config)

    # Отладочная информация
    db_uri = config.database_uri.get_secret_value()
    print(
        f"✓ Создан ToolManager для {app_name}: БД={db_uri}, role={config.role.value}, access_mode={config.access_mode.value}",
        flush=True,
    )

    # Регистрируем tools из ToolManager на подчиненном сервере
    tool_manager.register_tools(sub_mcp, prefix=app_name)

    return sub_mcp, tool_manager


def create_main_server() -> Starlette:
    """Создать главный сервер с кастомными tools и монтированными подчиненными серверами.

    Для монтирования разных серверов в разные endpoints:
    1. Создаем подчиненные FastMCP серверы с простыми tools
    2. Для каждого создаем http_app(path="/mcp") - получаем Starlette приложение
    3. Используем Starlette Mount для монтирования под разными путями
    4. Объединяем все в финальное Starlette приложение

    Returns:
        Starlette приложение с главным сервером и подчиненными.
    """
    # Создаем главный FastMCP сервер с кастомными tools
    main_mcp = FastMCP(name="MainServer")

    # Добавляем health check endpoint на главном сервере
    @main_mcp.custom_route("/health", methods=["GET"])
    async def health_check(_request: Request) -> JSONResponse:
        """Health check endpoint."""
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
        """Получить конфигурацию подчиненного сервера.

        Args:
            app_name: Имя подчиненного сервера (app1, app2, app3, app4).
        """
        if app_name not in SUB_SERVERS_CONFIG:
            return {
                "error": f"Server '{app_name}' not found",
                "available_servers": list(SUB_SERVERS_CONFIG.keys()),
            }

        config = SUB_SERVERS_CONFIG[app_name]
        db_uri = config.database_uri.get_secret_value()
        # Маскируем пароль в URI
        if "@" in db_uri and ":" in db_uri.split("@")[0]:
            parts = db_uri.split("@")
            user_pass = parts[0].split("://")[1]
            if ":" in user_pass:
                user = user_pass.split(":")[0]
                masked_uri = db_uri.replace(f"{user}:", f"{user}:***")
            else:
                masked_uri = db_uri
        else:
            masked_uri = db_uri

        return {
            "app_name": app_name,
            "role": config.role.value,
            "access_mode": config.access_mode.value,
            "database_uri": masked_uri,
            "pool_min_size": config.pool_min_size,
            "pool_max_size": config.pool_max_size,
            "safe_sql_timeout": config.safe_sql_timeout,
            "table_prefix": config.table_prefix,
        }

    @main_mcp.tool
    def list_all_servers() -> list[dict[str, Any]]:
        """Получить список всех серверов (главный + подчиненные) с их конфигурацией."""
        servers = [
            {
                "name": "MainServer",
                "type": "main",
                "endpoint": "/mcp",
                "tools_count": 4,  # get_server_info, get_sub_server_config, list_all_servers, calculate_stats
            }
        ]

        for app_name, config in SUB_SERVERS_CONFIG.items():
            # Определяем количество tools в зависимости от role
            if config.role == UserRole.USER:
                tools_count = 4  # list_objects, get_object_details, explain_query, execute_sql
            else:
                tools_count = 9  # все инструменты

            servers.append(
                {
                    "name": app_name,
                    "type": "sub",
                    "endpoint": f"/{app_name}/mcp",
                    "role": config.role.value,
                    "access_mode": config.access_mode.value,
                    "tools_count": tools_count,
                }
            )

        return servers

    @main_mcp.tool
    def calculate_stats(numbers: list[int]) -> dict[str, Any]:
        """Вычислить статистику для списка чисел.

        Args:
            numbers: Список целых чисел для анализа.
        """
        if not numbers:
            return {"error": "Список чисел не может быть пустым"}

        return {
            "count": len(numbers),
            "sum": sum(numbers),
            "average": sum(numbers) / len(numbers),
            "min": min(numbers),
            "max": max(numbers),
            "sorted": sorted(numbers),
        }

    # Создаем ToolManager для каждого подчиненного сервера
    tool_managers: dict[str, ToolManager] = {}
    sub_apps: list[tuple[str, Starlette]] = []

    for app_name, config in SUB_SERVERS_CONFIG.items():
        # Создаем подчиненный сервер с tools из ToolManager
        sub_mcp, tool_manager = create_sub_server(app_name, config)
        tool_managers[app_name] = tool_manager

        # Создаем ASGI приложение для подчиненного сервера через FastMCP
        # Используем путь /mcp (будет монтироваться под /app1/mcp и т.д.)
        sub_app = sub_mcp.http_app(path="/mcp")
        sub_apps.append((app_name, sub_app))

    # Создаем ASGI приложение из главного FastMCP сервера
    main_app = main_mcp.http_app(path="/mcp")

    # Создаем комбинированный lifespan для всех приложений
    # Каждое http_app() имеет свой lifespan, который нужно запустить
    @asynccontextmanager
    async def combined_lifespan(_app: Starlette) -> AsyncIterator[dict[str, Any]]:
        """Объединенный lifespan для всех FastMCP приложений и ToolManager."""
        async with AsyncExitStack() as stack:
            # Входим во все контекстные менеджеры ToolManager
            for tool_manager in tool_managers.values():
                await stack.enter_async_context(tool_manager)

            # Инициализируем подключения к базам данных
            print("Инициализация подключений к базам данных...")
            for app_name, tool_manager in tool_managers.items():
                try:
                    db_uri = tool_manager.config.database_uri.get_secret_value()
                    print(f"  Подключение {app_name} к БД: {db_uri}")
                    await tool_manager.db_connection.pool_connect()
                    # Проверяем, к какой БД действительно подключились
                    test_result = await tool_manager.sql_driver.execute_query("SELECT current_database() as db")
                    actual_db = test_result[0].cells["db"] if test_result else "unknown"
                    print(f"✓ Подключение к базе данных для {app_name} установлено (фактическая БД: {actual_db})")
                except Exception as e:
                    print(f"⚠ Не удалось подключиться к базе данных для {app_name}: {e}")

            # Запускаем lifespan всех подчиненных приложений
            for app_name, sub_app in sub_apps:
                if hasattr(sub_app, "lifespan") and sub_app.lifespan:
                    await stack.enter_async_context(sub_app.lifespan(_app))

            # Запускаем lifespan главного приложения
            if hasattr(main_app, "lifespan") and main_app.lifespan:
                await stack.enter_async_context(main_app.lifespan(_app))

            yield {}

    # Создаем Starlette приложение с монтированием подчиненных серверов
    # Каждый подчиненный сервер будет доступен по /{app_name}/mcp
    # Используем Starlette Mount для монтирования разных http_app() приложений
    routes = [
        # Монтируем каждый подчиненный сервер отдельно через Starlette Mount
        # Mount("/app1", app=...) означает, что приложение будет доступно по /app1/*
        # Так как sub_app создан с path="/mcp", итоговый путь будет /app1/mcp
        Mount(f"/{app_name}", app=sub_app)
        for app_name, sub_app in sub_apps
    ]
    routes.append(Mount("/", app=main_app))  # Главный сервер

    # Создаем финальное Starlette приложение с объединенным lifespan
    return Starlette(routes=routes, lifespan=combined_lifespan)


async def run_server() -> None:
    """Запустить сервер."""
    app = create_main_server()

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    print("=" * 60)
    print("Запуск тестового статического сервера")
    print("=" * 60)
    print("\nГлавный сервер:")
    print("  http://localhost:8000/")
    print("  http://localhost:8000/health")
    print("\nПодчиненные серверы:")
    for app_name in SUB_SERVERS_CONFIG:
        db_uri = SUB_SERVERS_CONFIG[app_name].database_uri.get_secret_value()
        print(f"  - {app_name}: http://localhost:8000/{app_name}/mcp")
        print(f"    БД: {db_uri}")
    print("\nДля проверки доступности инструментов используйте:")
    print("  curl -X POST http://localhost:8000/{app_name}/mcp \\")
    print("    -H 'Content-Type: application/json' \\")
    print('    -d \'{"jsonrpc":"2.0","method":"tools/list","id":1}\'')
    print("\nНажмите Ctrl+C для остановки")
    print("=" * 60)

    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        print("\nСервер остановлен")
