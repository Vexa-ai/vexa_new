.PHONY: up down build logs ps clean test run-bot help

help:
	@echo "Vexa Bot Management System - Development Commands"
	@echo ""
	@echo "Usage:"
	@echo "  make up             - Start all services (docker-compose up -d)"
	@echo "  make down           - Stop all services (docker-compose down)"
	@echo "  make build          - Build all services"
	@echo "  make logs           - Show logs from all services"
	@echo "  make logs-gateway   - Show logs from gateway service"
	@echo "  make logs-bot-manager - Show logs from bot-manager service"
	@echo "  make ps             - List running containers"
	@echo "  make clean          - Remove all containers and volumes"
	@echo "  make test           - Run a test bot"
	@echo "  make run-bot USER=user123 MEETING=meeting456 - Run a custom bot"

up:
	docker-compose up -d

down:
	docker-compose down

build:
	docker-compose build

logs:
	docker-compose logs -f

logs-gateway:
	docker-compose logs -f gateway

logs-bot-manager:
	docker-compose logs -f bot-manager

logs-transcription:
	docker-compose logs -f transcription-service

ps:
	docker-compose ps

clean:
	docker-compose down -v

test:
	docker-compose run --rm bot-test

run-bot:
	@if [ -z "$(USER)" ] || [ -z "$(MEETING)" ]; then \
		echo "Error: USER and MEETING parameters are required"; \
		echo "Usage: make run-bot USER=user123 MEETING=meeting456"; \
		exit 1; \
	fi
	docker-compose run --rm -e USER_ID=$(USER) -e MEETING_ID=$(MEETING) bot 