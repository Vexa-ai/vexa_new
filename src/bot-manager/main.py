import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging
import os
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Local imports
from app.database.models import init_db
from app.database.service import TranscriptionService
from app.tasks.monitoring import celery_app

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Determine environment and import appropriate client
ENVIRONMENT = os.getenv("ENVIRONMENT", "local").lower()

if ENVIRONMENT == "local" or ENVIRONMENT == "development":
    logger.info("Using Docker for container management (local development mode)")
    from app.docker.client import DockerClient
    container_client = DockerClient()
else:
    logger.info("Using Kubernetes for container management (production mode)")
    from app.kubernetes.client import KubernetesClient
    container_client = KubernetesClient()

# Initialize the FastAPI app
app = FastAPI(title="Bot Manager API", description="API for managing bot containers and transcriptions")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for request validation
class BotRunRequest(BaseModel):
    user_id: str
    meeting_id: str
    meeting_title: Optional[str] = None
    meeting_url: Optional[str] = "https://meet.google.com/xxx-xxxx-xxx"

class BotStopRequest(BaseModel):
    user_id: str
    meeting_id: Optional[str] = None

class TranscriptionRequest(BaseModel):
    meeting_id: str
    content: str
    speaker: Optional[str] = None
    confidence: Optional[int] = None

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    init_db()
    logger.info("Database initialized")

@app.get("/")
async def root():
    return {"message": "Bot Manager API is running", "environment": ENVIRONMENT}

@app.post("/bot/run")
async def run_bot(request: BotRunRequest, background_tasks: BackgroundTasks):
    """Start a new bot container for a user and meeting"""
    logger.info(f"Starting bot for user {request.user_id} and meeting {request.meeting_id} with URL {request.meeting_url}")
    
    try:
        # Start the bot container
        if ENVIRONMENT == "local" or ENVIRONMENT == "development":
            result = container_client.create_bot_container(
                request.user_id, 
                request.meeting_id,
                meeting_url=request.meeting_url
            )
        else:
            result = container_client.create_bot_pod(
                request.user_id, 
                request.meeting_id,
                meeting_url=request.meeting_url
            )
        
        # Create meeting record in database
        background_tasks.add_task(
            TranscriptionService.create_meeting,
            request.meeting_id,
            request.user_id,
            request.meeting_title
        )
        
        return {
            "status": "success",
            "message": f"Bot started for user {request.user_id}",
            "details": result
        }
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/bot/stop")
async def stop_bot(request: BotStopRequest, background_tasks: BackgroundTasks):
    """Stop a bot container or containers for a user"""
    logger.info(f"Stopping bot(s) for user {request.user_id}")
    
    try:
        # Stop the bot container(s)
        if ENVIRONMENT == "local" or ENVIRONMENT == "development":
            result = container_client.delete_bot_container(request.user_id, request.meeting_id)
        else:
            result = container_client.delete_bot_pod(request.user_id, request.meeting_id)
        
        # Mark meeting as ended if meeting_id is specified
        if request.meeting_id:
            background_tasks.add_task(
                TranscriptionService.end_meeting,
                request.meeting_id
            )
        
        return {
            "status": "success",
            "message": f"Bot(s) stopped for user {request.user_id}",
            "details": result
        }
    except Exception as e:
        logger.error(f"Error stopping bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/bot/status/{user_id}")
async def bot_status(user_id: str):
    """Get status of all bot containers for a user"""
    logger.info(f"Getting bot status for user {user_id}")
    
    try:
        result = container_client.get_bot_status(user_id)
        return {
            "status": "success",
            "bots": result
        }
    except Exception as e:
        logger.error(f"Error getting bot status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/transcription")
async def add_transcription(request: TranscriptionRequest):
    """Add a transcription to the database"""
    logger.info(f"Adding transcription for meeting {request.meeting_id}")
    
    try:
        transcription = TranscriptionService.add_transcription(
            request.meeting_id,
            request.content,
            request.speaker,
            request.confidence
        )
        
        if not transcription:
            raise HTTPException(status_code=404, detail=f"Meeting {request.meeting_id} not found")
        
        return {
            "status": "success",
            "message": "Transcription added"
        }
    except Exception as e:
        logger.error(f"Error adding transcription: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/transcript/{user_id}/{meeting_id}")
async def get_transcript(user_id: str, meeting_id: str):
    """Get all transcriptions for a meeting"""
    logger.info(f"Getting transcript for user {user_id}, meeting {meeting_id}")
    
    try:
        # Verify user has access to this meeting
        meetings = TranscriptionService.get_user_meetings(user_id)
        meeting_ids = [m["id"] for m in meetings]
        
        if meeting_id not in meeting_ids:
            raise HTTPException(status_code=403, detail="User does not have access to this meeting")
        
        transcriptions = TranscriptionService.get_meeting_transcriptions(meeting_id)
        
        return {
            "status": "success",
            "meeting_id": meeting_id,
            "user_id": user_id,
            "transcriptions": transcriptions
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting transcript: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/meetings/{user_id}")
async def get_user_meetings(user_id: str):
    """Get all meetings for a user"""
    logger.info(f"Getting meetings for user {user_id}")
    
    try:
        meetings = TranscriptionService.get_user_meetings(user_id)
        
        return {
            "status": "success",
            "user_id": user_id,
            "meetings": meetings
        }
    except Exception as e:
        logger.error(f"Error getting meetings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True) 