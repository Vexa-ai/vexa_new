.PHONY: all setup submodules env download-model build-bot-image build up down clean ps logs

# Default target: Sets up everything and starts the services
all: setup build up

# Target to perform all initial setup steps
setup: submodules env download-model build-bot-image
	@echo "Setup complete. Please ensure you have edited the .env file."

# Initialize and update Git submodules
submodules:
	@echo "---> Initializing and updating Git submodules..."
	@git submodule update --init --recursive

# Create .env file from example
env:
	@echo "---> Creating .env file..."
	@if [ ! -f .env ]; then \
		cp env-example .env; \
		echo "*** .env file created. Please edit it with your configuration. ***"; \
	else \
		echo ".env file already exists. Skipping creation."; \
	fi

# Download the Whisper model
download-model:
	@echo "---> Downloading Whisper model (this may take a while)..."
	@python download_model.py

# Build the standalone vexa-bot image
build-bot-image:
	@echo "---> Building vexa-bot:latest image..."
	@docker build -t vexa-bot:latest -f services/vexa-bot/core/Dockerfile ./services/vexa-bot/core

# Build Docker Compose service images (excluding vexa-bot)
build:
	@echo "---> Building Docker Compose services..."
	@docker compose build

# Start services in detached mode
up:
	@echo "---> Starting Docker Compose services..."
	@docker compose up -d

# Stop services
down:
	@echo "---> Stopping Docker Compose services..."
	@docker compose down

# Stop services and remove volumes
clean:
	@echo "---> Stopping Docker Compose services and removing volumes..."
	@docker compose down -v

# Show container status
ps:
	@docker compose ps

# Tail logs for all services
logs:
	@docker compose logs -f
