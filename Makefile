
.PHONY: help lint format clean commit push release-patch release-minor release-major

help: ## Показать справку по командам
	@echo "Доступные команды:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

lint: ## Проверить код линтерами (ruff + mypy)
	uv run ruff check .
	uv run mypy src/

format: ## Отформатировать код (ruff format + автофиксы)
	uv run ruff format .
	uv run ruff check --fix .

clean: ## Очистить артефакты сборки и кэши
	rm -rf dist/ build/ *.egg-info/ .pytest_cache/ .ruff_cache/ .mypy_cache/ .coverage htmlcov/

# Управление версиями

release-patch: ## Релиз PATCH версии (clean → sync → bump → commit → push → merge)
	@echo "Запускаю релиз PATCH версии..."
	@echo "Очищаю артефакты сборки..."
	$(MAKE) clean
	@echo "Синхронизирую зависимости..."
	uv sync
	@echo "Увеличиваю PATCH версию..."
	uv version --bump patch
	@NEW_VERSION=$$(uv version --short); \
	echo "Новая версия: $$NEW_VERSION"; \
	echo "Обновляю локальный репозиторий..."; \
	git pull; \
	git add .; \
	git commit -m "Release v$$NEW_VERSION"; \
	git push; \
	echo "Релиз v$$NEW_VERSION создан и отправлен!"; \
	echo "Теперь создайте Merge Request в main ветку"

release-minor: ## Релиз MINOR версии (clean → sync → bump → commit → push → merge)
	@echo "Запускаю релиз MINOR версии..."
	@echo "Очищаю артефакты сборки..."
	$(MAKE) clean
	@echo "Синхронизирую зависимости..."
	uv sync
	@echo "Увеличиваю MINOR версию..."
	uv version --bump minor
	@NEW_VERSION=$$(uv version --short); \
	echo "Новая версия: $$NEW_VERSION"; \
	echo "Обновляю локальный репозиторий..."; \
	git pull; \
	git add .; \
	git commit -m "Release v$$NEW_VERSION"; \
	git push; \
	echo "Релиз v$$NEW_VERSION создан и отправлен!"; \
	echo "Теперь создайте Merge Request в main ветку"

release-major: ## Релиз MAJOR версии (clean → sync → bump → commit → push → merge)
	@echo "Запускаю релиз MAJOR версии..."
	@echo "Очищаю артефакты сборки..."
	$(MAKE) clean
	@echo "Синхронизирую зависимости..."
	uv sync
	@echo "Увеличиваю MAJOR версию..."
	uv version --bump major
	@NEW_VERSION=$$(uv version --short); \
	echo "Новая версия: $$NEW_VERSION"; \
	echo "Обновляю локальный репозиторий..."; \
	git pull; \
	git add .; \
	git commit -m "Release v$$NEW_VERSION"; \
	git push; \
	echo "Релиз v$$NEW_VERSION создан и отправлен!"; \
	echo "Теперь создайте Merge Request в main ветку"

# Git команды
commit: ## Сделать коммит с сообщением (интерактивно запрашивает сообщение)
	@echo "📝 Введите сообщение для коммита:"
	@read -p "Сообщение: " msg; \
	echo "🔄 Обновляю локальный репозиторий..."; \
	git pull; \
	git add .; \
	git commit -m "$$msg"; \
	echo "✅ Коммит создан!"

push: ## Сделать коммит и пуш (интерактивно запрашивает сообщение)
	@echo "📝 Введите сообщение для коммита:"
	@read -p "Сообщение: " msg; \
	echo "🔄 Обновляю локальный репозиторий..."; \
	git pull; \
	git add .; \
	git commit -m "$$msg"; \
	git push; \
	echo "✅ Коммит создан и отправлен в удаленный репозиторий!"

run-mcp: ## Запустить MCP сервер
	uv run python mcp_server.py


# Специальные правила для обработки аргументов
%:
	@:
