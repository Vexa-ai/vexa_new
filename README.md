# Vexa - Meeting Bot & Transcription System

A microservices-based system for deploying and managing meeting bots (Vexa Bot) that join meetings, stream audio for live transcription using Whisper, filter transcriptions, and store the results.

## Architecture

The system consists of several key microservices orchestrated via Docker Compose (for development) and designed for Kubernetes (Helm charts pending):

1.  **API Gateway (`api-gateway`)** - The main entry point (`http://localhost:8056`) for client requests, routing to downstream services and handling initial authentication checks.
2.  **Admin API (`admin-api`)** - Handles administrative tasks like user creation and API token generation. Accessible directly during development (`http://localhost:8057`) or via the gateway (`/admin` routes). Requires `X-Admin-API-Key` header.
3.  **Bot Manager (`bot-manager`)** - Manages the lifecycle of Vexa Bot containers, interacting with the Docker daemon to start/stop bots based on API requests. Requires `X-API-Key` header via the gateway.
4.  **Transcription Collector (`transcription-collector`)** - Receives transcription segments via WebSocket from WhisperLive, filters them for relevance, and stores them in PostgreSQL.
5.  **WhisperLive (`whisperlive`)** - Performs live speech-to-text transcription using GPU resources (requires NVIDIA Docker setup). Streams results to the Transcription Collector. Accessible directly for debugging (`http://localhost:9090`).
6.  **Vexa Bot Image (`vexa-bot:latest`)** - The Docker image for the actual bot (built from `services/vexa-bot/core`). This image is *not* run as a service in Docker Compose but is launched on demand by the Bot Manager.
7.  **Redis** - Used for caching, locking (Bot Manager), and potentially inter-service communication.
8.  **PostgreSQL (`postgres`)** - Primary database for storing user data, API tokens, and filtered transcriptions.

## Local Development Setup

### Prerequisites

-   Docker and Docker Compose installed
-   Git (with Git LFS potentially needed by submodules)
-   Python 3.x (for the model download script)
-   NVIDIA Container Toolkit (if using `whisperlive` with GPU acceleration)

### Getting Started

1.  **Clone the Repository:**
    ```bash
    git clone <repository-url> vexa
    cd vexa
    ```

2.  **Initialize Submodules:**
    This project uses Git submodules (`services/vexa-bot` and `services/WhisperLive`). Initialize and clone them:
    ```bash
    git submodule update --init --recursive
    ```

3.  **Configure Environment:**
    Create a `.env` file from the example and customize it with your settings (especially `ADMIN_API_TOKEN`).
    ```bash
    cp env-example .env
    # Now edit the .env file with your preferred editor
    nano .env
    ```

4.  **Download Whisper Model:**
    The `whisperlive` service requires a pre-trained Whisper model. Run the provided script to download it (adjust model name in script/compose file if needed).
    ```bash
    python download_model.py
    ```
    This will download the model to the `./hub` directory, which is mounted into the `whisperlive` container.

5.  **Build Vexa Bot Image:**
    The Vexa Bot image needs to be built manually before starting the system, as it's launched dynamically by the Bot Manager. Ensure submodules are initialized first (Step 2).
    ```bash
    docker build -t vexa-bot:latest -f services/vexa-bot/core/Dockerfile ./services/vexa-bot/core
    ```

6.  **Build and Start Services:**
    Use Docker Compose to build the other service images and start the system. It will use the values from your `.env` file.
    ```bash
    # Build service images (excluding vexa-bot which was built in the previous step)
    docker compose build

    # Start all services in detached mode
    docker compose up -d
    ```
    This will start all services defined in `docker-compose.yml`.

7.  **Accessing Services:**
    *   **Main API:** `http://localhost:8056` (API Gateway)
    *   **Admin API (Direct Dev Access):** `http://localhost:8057`
    *   **WhisperLive (Debug):** `http://localhost:9090`
    *   **Transcription Collector (Debug):** `http://localhost:8123` (Maps to container port 8000)
    *   **PostgreSQL (Direct Dev Access):** `localhost:5438` (Maps to container port 5432)
    Internal services (Bot Manager, Transcription Collector, Redis, Postgres) communicate over the Docker network and are not directly exposed by default (except for the debug/direct access ports listed above).

8.  **Check Status:**
```bash
docker-compose ps
```

9.  **View Logs:**
```bash
    # Tail logs for all services
    docker-compose logs -f

    # Tail logs for a specific service
    docker-compose logs -f api-gateway
    docker-compose logs -f bot-manager
    # etc...
    ```

### API Usage (Development)

*   **Admin Operations:** Access via `http://localhost:8057` or `http://localhost:8056/admin/...`. Requires the `X-Admin-API-Key` header (value set as `ADMIN_API_TOKEN` in the project's `.env` file - see Step 3 in Getting Started).
    *   Example: `curl -H "X-Admin-API-Key: YOUR_ADMIN_TOKEN_FROM_DOTENV" http://localhost:8057/admin/users`
*   **Client Operations:** Access via the gateway `http://localhost:8056`. Requires the `X-API-Key` header (value corresponds to a token generated via the admin API).
    *   Example (Request Bot):
```