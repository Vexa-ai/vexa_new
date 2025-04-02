import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import logging
import os
import base64
from typing import Optional
# Remove dotenv loading if not strictly needed, rely on docker-compose env vars
# from dotenv import load_dotenv 

# Load environment variables
# load_dotenv()

# Local imports - Remove unused ones
# from app.database.models import init_db # Using local init_db now
# from app.database.service import TranscriptionService # Not used here
# from app.tasks.monitoring import celery_app # Not used here

from .config import BOT_IMAGE_NAME, REDIS_URL
from .redis_utils import (
    generate_meeting_id, acquire_lock, release_lock,
    store_container_mapping, get_container_id_for_meeting,
    init_redis, close_redis, extract_platform_specific_id
)
from .docker_utils import get_socket_session, close_docker_client, start_bot_container, stop_bot_container
from .database import init_db, get_db, User, APIToken # Import DB items
from .auth import get_current_user # Import auth dependency
from sqlalchemy.ext.asyncio import AsyncSession
from admin import router as admin_router # Import the admin router

# Configure logging
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("bot_manager")

# Determine environment and import appropriate client - Remove K8s/Docker switch logic
# ENVIRONMENT = os.getenv("ENVIRONMENT", "local").lower()
# if ENVIRONMENT == "local" or ENVIRONMENT == "development":
#     logger.info("Using Docker for container management (local development mode)")
#     from app.docker.client import DockerClient
#     container_client = DockerClient()
# else:
#     logger.info("Using Kubernetes for container management (production mode)")
#     from app.kubernetes.client import KubernetesClient
#     container_client = KubernetesClient()

# Initialize the FastAPI app
app = FastAPI(title="Vexa Bot Manager")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for request validation
class BotRequest(BaseModel):
    platform: str = Field(..., description="Platform identifier (e.g., 'google_meet', 'zoom')")
    meeting_url: str = Field(..., description="The full meeting URL for the bot to join")
    token: str = Field(..., description="The unique token identifying the customer/request context")
    bot_name: Optional[str] = Field(None, description="Optional name for the bot in the meeting")

class BotResponse(BaseModel):
    status: str
    message: str
    meeting_id: Optional[str] = None # Now uses the platform:platform_id:token format
    container_id: Optional[str] = None

# Remove unused models
# class BotRunRequest(BaseModel):
#     user_id: str
#     meeting_id: str
#     meeting_title: Optional[str] = None
#     meeting_url: Optional[str] = "https://meet.google.com/xxx-xxxx-xxx"

# class BotStopRequest(BaseModel):
#     user_id: str
#     meeting_id: Optional[str] = None

# class TranscriptionRequest(BaseModel):
#     meeting_id: str
#     content: str
#     speaker: Optional[str] = None
#     confidence: Optional[int] = None

@app.on_event("startup")
async def startup_event():
    logger.info("Starting up Bot Manager...")
    await init_db() 
    await init_redis()
    get_socket_session()
    logger.info("Database, Redis and Socket Session initialized.")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down Bot Manager...")
    await close_redis()
    close_docker_client() 
    logger.info("Redis and Socket Session closed.")

@app.get("/", include_in_schema=False) # Hide root from docs for now
async def root():
    # Keep simple root for basic health/status check if needed
    return {"message": "Vexa Bot Manager is running"}

@app.post("/bots", 
          response_model=BotResponse,
          status_code=status.HTTP_201_CREATED,
          summary="Request a new bot instance to join a meeting",
          dependencies=[Depends(get_current_user)]) # Apply authentication
async def request_bot(req: BotRequest, current_user: User = Depends(get_current_user)):
    """Handles requests to launch a new bot container for a meeting.
    Requires a valid API token associated with a user.
    - Generates a unique meeting ID.
    - Attempts to acquire a lock in Redis for this meeting ID.
    - If lock acquired, starts a Docker container for the bot.
    - Stores mapping between meeting ID and container ID.
    - Returns container ID and status.
    - If lock not acquired, indicates that a bot is already running.
    """
    logger.info(f"Received bot request for platform '{req.platform}' from user {current_user.id}")

    # 1. Extract platform-specific ID from URL
    platform_specific_id = extract_platform_specific_id(req.platform, req.meeting_url)
    if not platform_specific_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not extract a valid meeting identifier from the URL '{req.meeting_url}' for platform '{req.platform}'."
        )

    # 2. Generate the standardized meeting ID
    try:
        meeting_id = generate_meeting_id(req.platform, platform_specific_id, req.token)
        logger.info(f"Generated meeting_id: {meeting_id}")
    except ValueError as e:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # 3. Try to acquire the lock
    if not await acquire_lock(meeting_id):
        # Could check TTL here if needed, but acquire_lock logs it.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"status": "conflict", "message": f"A bot is already active or starting for meeting ID {meeting_id}.", "meeting_id": meeting_id}
        )

    # 4. Start the bot container (passing full URL and specific BOT_IMAGE_NAME)
    try:
        container_id = start_bot_container(
            meeting_url=req.meeting_url, 
            platform=req.platform,
            token=req.token,
            bot_name=req.bot_name,
        )
        
        if not container_id:
            # If starting failed, release the lock
            await release_lock(meeting_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail={"status": "error", "message": "Failed to start bot container.", "meeting_id": meeting_id}
            )

        # 5. Store the mapping if container started successfully
        await store_container_mapping(meeting_id, container_id)

        logger.info(f"Successfully started bot container {container_id} for meeting_id {meeting_id}")
        return BotResponse(
            status="started",
            message="Bot container started successfully.",
            meeting_id=meeting_id,
            container_id=container_id
        )

    except Exception as e:
        # Generic error handling: Release lock and report
        logger.error(f"Error during bot startup process for meeting_id {meeting_id}: {e}", exc_info=True)
        await release_lock(meeting_id) # Ensure lock is released on failure
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail={"status": "error", "message": f"An unexpected error occurred: {str(e)}", "meeting_id": meeting_id}
        )

@app.delete("/bots/{platform}/{platform_specific_id}/{token}",
             status_code=status.HTTP_200_OK,
             response_model=BotResponse,
             summary="Stop a running bot for a specific meeting")
async def stop_bot(platform: str, platform_specific_id: str, token: str, 
                   current_user: User = Depends(get_current_user)): # Protect endpoint
    """Stops the bot container associated with the meeting ID and releases the lock."""
    try:
        # 1. Generate the meeting ID from path parameters
        meeting_id = generate_meeting_id(platform, platform_specific_id, token)
        logger.info(f"User {current_user.id} requested to stop bot for meeting_id: {meeting_id}")

        # 2. Find the container ID from Redis mapping
        container_id = await get_container_id_for_meeting(meeting_id)
        
        stop_success = True # Assume success unless stop fails or no container found
        response_message = f"Stop request processed for meeting ID {meeting_id}."
        response_status = "stopped"

        if not container_id:
            logger.warning(f"No active bot container mapping found for meeting_id: {meeting_id}. Releasing lock only.")
            response_message = f"No active bot mapping found for meeting ID {meeting_id}, lock released."
            response_status = "not_found" # Indicate mapping wasn't found
            stop_success = False # Technically didn't stop anything
        else:
            # 3. Stop the container if found
            logger.info(f"Attempting to stop container {container_id} for meeting_id: {meeting_id}")
            stopped = stop_bot_container(container_id)
            
            if not stopped:
                # Log error but proceed to release lock anyway
                logger.error(f"Stop command failed or container {container_id} not found by Docker. Proceeding to release lock.")
                # Even if stop fails, we proceed with lock release. Maybe container is already gone.
                response_message = f"Stop command failed for container {container_id} (it might be already stopped/gone). Lock released."
                response_status = "stop_failed"
                stop_success = False
            else:
                 response_message = f"Stop command successfully sent to container {container_id}. Lock released."
                 response_status = "stopped"

        # 4. Release the lock and mapping from Redis (always attempt this)
        await release_lock(meeting_id)
        
        return BotResponse(
            status=response_status,
            message=response_message,
            meeting_id=meeting_id,
            container_id=container_id # Return the ID even if stop failed, for reference
        )

    except ValueError as e: # Catch specific error from generate_meeting_id
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid components for meeting_id: {str(e)}")
    except Exception as e:
        logger.error(f"Error stopping bot for {platform}/{platform_specific_id}/{token}: {e}", exc_info=True)
        # Try to generate meeting_id for the error response if possible
        try: 
            m_id = generate_meeting_id(platform, platform_specific_id, token)
        except: 
            m_id = f"{platform}:{platform_specific_id}:{token}" # Fallback
        raise HTTPException(status_code=500, detail={"status": "error", "message": str(e), "meeting_id": m_id})

# --- Remove Temporary Debug Endpoint --- 
# @app.delete("/debug/locks/{platform}/{meeting_url_b64}/{token}", ...)
# async def debug_release_lock(...):
#    ...

# --- Remove or Refactor Old Endpoints --- 
# @app.post("/bot/run")
# async def run_bot(...):
#     ...

# @app.post("/bot/stop")
# async def stop_bot(...):
#     ...

# @app.get("/bot/status/{user_id}")
# async def bot_status(...):
#     ...

# @app.post("/transcription")
# async def add_transcription(...):
#     ...

# @app.get("/transcript/{user_id}/{meeting_id}")
# async def get_transcript(...):
#     ...

# @app.get("/meetings/{user_id}")
# async def get_user_meetings(...):
#     ...

# Include admin router FIRST to ensure prefix works correctly
app.include_router(admin_router)

if __name__ == "__main__":
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8080, # Default port for bot-manager
        reload=True, # Enable reload for development
        log_level=logging.getLogger().level
    ) 