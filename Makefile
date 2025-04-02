.PHONY: up down build logs ps clean test run-bot help clone-bot-repo setup

help:
	@echo "Vexa Bot Management System - Development Commands"
	@echo ""
	@echo "Usage:"
	@echo "  make setup          - Clone Vexa Bot repo and setup environment"
	@echo "  make up             - Start all services (docker-compose up -d)"
	@echo "  make down           - Stop all services (docker-compose down)"
	@echo "  make build          - Build all services"
	@echo "  make logs           - Show logs from all services"
	@echo "  make logs-gateway   - Show logs from gateway service"
	@echo "  make logs-bot-manager - Show logs from bot-manager service"
	@echo "  make ps             - List running containers"
	@echo "  make clean          - Remove all containers and volumes"
	@echo "  make test           - Run a test bot"
	@echo "  make run-bot USER=user123 MEETING=meeting456 MEETING_URL=https://meet.google.com/xxx-xxxx-xxx - Run a custom bot"

setup: clone-bot-repo
	@echo "Setup complete. You can now run 'make build' and 'make up'"

clone-bot-repo:
	@echo "Cloning Vexa Bot repository..."
	@if [ -d "vexa-bot" ]; then \
		echo "Vexa Bot repository already exists"; \
	else \
		git clone https://github.com/Vexa-ai/vexa-bot.git; \
	fi

up:
	docker-compose up -d

down:
	docker-compose down

build: clone-bot-repo
	docker-compose build

logs:
	docker-compose logs -f

logs-gateway:
	docker-compose logs -f gateway

logs-bot-manager:
	docker-compose logs -f bot-manager

logs-transcription:
	docker-compose logs -f transcription-service

logs-bot:
	docker-compose logs -f bot

ps:
	docker-compose ps

clean:
	docker-compose down -v

test: clone-bot-repo
	docker-compose run --rm bot-test

run-bot: clone-bot-repo
	@if [ -z "$(USER)" ] || [ -z "$(MEETING)" ]; then \
		echo "Error: USER and MEETING parameters are required"; \
		echo "Usage: make run-bot USER=user123 MEETING=meeting456 MEETING_URL=https://meet.google.com/xxx-xxxx-xxx"; \
		exit 1; \
	fi
	docker-compose run --rm -e USER_ID=$(USER) -e MEETING_ID=$(MEETING) -e MEETING_URL=$(MEETING_URL) bot 