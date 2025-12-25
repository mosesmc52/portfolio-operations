# ================================
# Portfolio Operations Makefile
# Full drop-in replacement
# ================================

# Use bash for better scripting (pipefail, functions, etc.)
SHELL := /bin/bash
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c

# ---- Configurable Variables ----
PROJECT        ?= portfolio-operations
COMPOSE        ?= docker compose
LOCAL_FILE     ?= docker-compose.local.yml
PROD_FILE      ?= docker-compose.yml
SERVICE        ?= web

# Django management entrypoints
DJANGO_MANAGE  ?= python manage.py
DJANGO_SHELL   ?= shell

# Log controls
# Examples:
#   make logs                # local, follow, all services
#   make logs SERVICE=web    # local, follow, one service
#   make logs LINES=200      # local, follow, last 200 lines
#   make prod-logs           # production, follow
LINES          ?= 200
FOLLOW         ?= 1

# Internal helpers
LOCAL_STACK = -p $(PROJECT)-local -f $(LOCAL_FILE)
PROD_STACK  = -p $(PROJECT) -f $(PROD_FILE)

.PHONY: help
help:
	@echo ""
	@echo "Usage:"
	@echo "  make local-up              Start local stack (foreground)"
	@echo "  make local-up-d            Start local stack (detached)"
	@echo "  make local-down            Stop local stack"
	@echo "  make local-build           Build local images"
	@echo "  make local-restart         Restart local stack"
	@echo ""
	@echo "  make prod-up               Start production stack (detached)"
	@echo "  make prod-down             Stop production stack"
	@echo "  make prod-build            Build production images"
	@echo "  make prod-restart          Restart production stack"
	@echo ""
	@echo "  make logs                  Tail local logs (all or SERVICE=...)"
	@echo "  make prod-logs             Tail production logs (all or SERVICE=...)"
	@echo ""
	@echo "  make shell                 Open Django shell (local)"
	@echo "  make bash                  Open bash in the container (local)"
	@echo "  make manage CMD='check'    Run manage.py command (local)"
	@echo "  make migrate               Run migrations (local)"
	@echo "  make makemigrations        Make migrations (local)"
	@echo "  make createsuperuser       Create Django admin user (local)"
	@echo ""
	@echo "  make clean                 Stop local stack (keep volumes)"
	@echo "  make clean-prod            Stop production stack (keep volumes)"
	@echo "  make clean-all             FULL local reset (delete volumes)"
	@echo "  make clean-images          Remove unused Docker images"
	@echo "  make clean-system          Nuclear Docker reset"
	@echo ""

# ================================
# Local Environment
# ================================

.PHONY: local-up
local-up:
	$(COMPOSE) $(LOCAL_STACK) up

.PHONY: local-down
local-down:
	$(COMPOSE) $(LOCAL_STACK) down

.PHONY: local-build
local-build:
	$(COMPOSE) $(LOCAL_STACK) build

.PHONY: local-restart
local-restart: local-down local-up-d

# ================================
# Production Environment
# ================================

.PHONY: prod-up
prod-up:
	$(COMPOSE) $(PROD_STACK) up -d

.PHONY: prod-down
prod-down:
	$(COMPOSE) $(PROD_STACK) down

.PHONY: prod-build
prod-build:
	$(COMPOSE) $(PROD_STACK) build

.PHONY: prod-restart
prod-restart: prod-down prod-up

# ================================
# Logs
# ================================

# Local logs (follow by default). If SERVICE is set, only that service is tailed.
.PHONY: logs
logs:
	if [[ -n "${SERVICE:-}" ]]; then \
		if [[ "$(FOLLOW)" == "1" ]]; then \
			$(COMPOSE) $(LOCAL_STACK) logs -f --tail=$(LINES) $(SERVICE); \
		else \
			$(COMPOSE) $(LOCAL_STACK) logs --tail=$(LINES) $(SERVICE); \
		fi; \
	else \
		if [[ "$(FOLLOW)" == "1" ]]; then \
			$(COMPOSE) $(LOCAL_STACK) logs -f --tail=$(LINES); \
		else \
			$(COMPOSE) $(LOCAL_STACK) logs --tail=$(LINES); \
		fi; \
	fi

# Production logs (follow by default). If SERVICE is set, only that service is tailed.
.PHONY: prod-logs
prod-logs:
	if [[ -n "${SERVICE:-}" ]]; then \
		if [[ "$(FOLLOW)" == "1" ]]; then \
			$(COMPOSE) $(PROD_STACK) logs -f --tail=$(LINES) $(SERVICE); \
		else \
			$(COMPOSE) $(PROD_STACK) logs --tail=$(LINES) $(SERVICE); \
		fi; \
	else \
		if [[ "$(FOLLOW)" == "1" ]]; then \
			$(COMPOSE) $(PROD_STACK) logs -f --tail=$(LINES); \
		else \
			$(COMPOSE) $(PROD_STACK) logs --tail=$(LINES); \
		fi; \
	fi

# ================================
# Django Management (Local)
# ================================

# Open Django shell
.PHONY: shell
shell:
	$(COMPOSE) $(LOCAL_STACK) exec $(SERVICE) $(DJANGO_MANAGE) $(DJANGO_SHELL)

# Open an interactive bash session in the service container
.PHONY: bash
bash:
	$(COMPOSE) $(LOCAL_STACK) exec $(SERVICE) bash

# Run arbitrary manage.py commands:
#   make manage CMD="check"
#   make manage CMD="createsuperuser"
#   make manage CMD="dbshell"
.PHONY: manage
manage:
	: $${CMD:?Usage: make manage CMD='your_command [args]'}
	$(COMPOSE) $(LOCAL_STACK) exec $(SERVICE) $(DJANGO_MANAGE) $$CMD

.PHONY: migrate
migrate:
	$(COMPOSE) $(LOCAL_STACK) exec $(SERVICE) $(DJANGO_MANAGE) migrate

.PHONY: makemigrations
makemigrations:
	$(COMPOSE) $(LOCAL_STACK) exec $(SERVICE) $(DJANGO_MANAGE) makemigrations

.PHONY: createsuperuser
createsuperuser:
	$(COMPOSE) $(LOCAL_STACK) exec $(SERVICE) $(DJANGO_MANAGE) createsuperuser

# ================================
# Cleanup Targets
# ================================

.PHONY: clean
clean:
	@echo "Stopping local stack and removing containers (volumes preserved)"
	$(COMPOSE) $(LOCAL_STACK) down --remove-orphans

.PHONY: clean-prod
clean-prod:
	@echo "Stopping production stack and removing containers (volumes preserved)"
	$(COMPOSE) $(PROD_STACK) down --remove-orphans

.PHONY: clean-all
clean-all:
	@echo "Removing containers, networks, and volumes (FULL RESET)"
	$(COMPOSE) $(LOCAL_STACK) down --volumes --remove-orphans

.PHONY: clean-images
clean-images:
	@echo "Removing unused Docker images"
	docker image prune -f

.PHONY: clean-system
clean-system:
	@echo "FULL Docker system prune (containers, images, networks, volumes)"
	docker system prune -a --volumes
