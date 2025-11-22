.PHONY: help lint format clean commit push release-patch release-minor release-major test docker-up docker-down docker-build docker-release docker-push

ifneq (,$(wildcard .env))
    $(foreach line,$(shell grep -E '^DOCKER_(IMAGE|TAG)=' .env 2>/dev/null),$(eval $(line)))
endif

# Docker image configuration (can be overridden via .env or command line)
DOCKER_IMAGE ?= postgres-fastmcp
DOCKER_TAG ?= latest
DOCKER_FULL_IMAGE := $(DOCKER_IMAGE):$(DOCKER_TAG)

help: ## Show help for available commands
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

lint: ## Check code with linters (ruff + mypy)
	uv run ruff check .
	uv run mypy src/

format: ## Format code (ruff format + auto-fixes)
	uv run ruff format .
	uv run ruff check --fix .

clean: ## Clean build artifacts and caches
	rm -rf dist/ build/ *.egg-info/ .pytest_cache/ .ruff_cache/ .mypy_cache/ .coverage htmlcov/

test: ## Run all tests
	uv run python -m pytest

test-unit: ## Run unit tests only
	uv run python -m pytest tests/unit/

test-integration: ## Run integration tests only
	uv run python -m pytest tests/integration/

# Version management

release-patch: ## Release PATCH version (clean → sync → bump → commit → push → merge)
	@echo "Starting PATCH version release..."
	@echo "Cleaning build artifacts..."
	$(MAKE) clean
	@echo "Synchronizing dependencies..."
	uv sync
	@echo "Bumping PATCH version..."
	uv version --bump patch
	@NEW_VERSION=$$(uv version --short); \
	echo "New version: $$NEW_VERSION"; \
	echo "Updating local repository..."; \
	git pull; \
	git add .; \
	git commit -m "Release v$$NEW_VERSION"; \
	git push; \
	echo "Release v$$NEW_VERSION created and pushed!"; \
	echo "Now create a Merge Request to the main branch"

release-minor: ## Release MINOR version (clean → sync → bump → commit → push → merge)
	@echo "Starting MINOR version release..."
	@echo "Cleaning build artifacts..."
	$(MAKE) clean
	@echo "Synchronizing dependencies..."
	uv sync
	@echo "Bumping MINOR version..."
	uv version --bump minor
	@NEW_VERSION=$$(uv version --short); \
	echo "New version: $$NEW_VERSION"; \
	echo "Updating local repository..."; \
	git pull; \
	git add .; \
	git commit -m "Release v$$NEW_VERSION"; \
	git push; \
	echo "Release v$$NEW_VERSION created and pushed!"; \
	echo "Now create a Merge Request to the main branch"

release-major: ## Release MAJOR version (clean → sync → bump → commit → push → merge)
	@echo "Starting MAJOR version release..."
	@echo "Cleaning build artifacts..."
	$(MAKE) clean
	@echo "Synchronizing dependencies..."
	uv sync
	@echo "Bumping MAJOR version..."
	uv version --bump major
	@NEW_VERSION=$$(uv version --short); \
	echo "New version: $$NEW_VERSION"; \
	echo "Updating local repository..."; \
	git pull; \
	git add .; \
	git commit -m "Release v$$NEW_VERSION"; \
	git push; \
	echo "Release v$$NEW_VERSION created and pushed!"; \
	echo "Now create a Merge Request to the main branch"

# Git commands

commit: ## Make a commit with message (interactively prompts for message)
	@echo "📝 Enter commit message:"
	@read -p "Message: " msg; \
	echo "🔄 Updating local repository..."; \
	git pull; \
	git add .; \
	git commit -m "$$msg"; \
	echo "✅ Commit created!"

push: ## Make a commit and push (interactively prompts for message)
	@echo "📝 Enter commit message:"
	@read -p "Message: " msg; \
	echo "🔄 Updating local repository..."; \
	git pull; \
	git add .; \
	git commit -m "$$msg"; \
	git push; \
	echo "✅ Commit created and pushed to remote repository!"

# Docker commands

docker-build: ## Build Docker image (reads DOCKER_IMAGE and DOCKER_TAG from .env)
	@echo "🐳 Building Docker image $(DOCKER_FULL_IMAGE)..."
	docker buildx build --platform=linux/amd64 --provenance=false --sbom=false -t $(DOCKER_FULL_IMAGE) --load -f Dockerfile .
	@echo "✅ Docker image $(DOCKER_FULL_IMAGE) built successfully!"

docker-release: ## Build and push Docker image to registry (reads from .env)
	@echo "🚀 Building and publishing $(DOCKER_FULL_IMAGE)..."
	docker buildx build --platform=linux/amd64 --provenance=false --sbom=false -t $(DOCKER_FULL_IMAGE) --load -f Dockerfile .
	@echo "📤 Pushing image to registry..."
	docker push $(DOCKER_FULL_IMAGE)
	@echo "✅ Image published: $(DOCKER_FULL_IMAGE)"

docker-push: ## Push previously built Docker image to registry (reads from .env)
	@echo "📤 Pushing image $(DOCKER_FULL_IMAGE) to registry..."
	docker push $(DOCKER_FULL_IMAGE)
	@echo "✅ Image pushed: $(DOCKER_FULL_IMAGE)"

docker-up: ## Start Docker test environment
	docker-compose up -d --build

docker-down: ## Stop Docker test environment
	docker-compose down

docker-logs: ## View Docker logs
	docker-compose logs -f

docker-clean: ## Stop Docker environment and remove volumes
	docker-compose down -v

# Special rule for handling arguments
%:
	@:
