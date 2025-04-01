import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging
import os
import httpx
from typing import Optional, List
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(title="Transcription Service", description="Service for processing transcriptions")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get environment variables
BOT_MANAGER_URL = os.getenv("BOT_MANAGER_URL", "http://bot-manager-service:8080")

# Pydantic models
class TranscriptionRequest(BaseModel):
    meeting_id: str
    content: str
    speaker: Optional[str] = None
    confidence: Optional[int] = None

@app.get("/")
async def root():
    return {"message": "Transcription Service is running"}

@app.post("/transcription")
async def process_transcription(request: TranscriptionRequest):
    """
    Process a transcription from a bot and forward it to the Bot Manager API
    
    In a real load-balanced implementation, this would:
    1. Receive the raw audio from the bot
    2. Process it using a transcription engine (e.g., Google Speech-to-Text)
    3. Store the resulting transcription in the database
    
    For this example, we'll assume the bot has already done the transcription
    and we just need to forward it to the Bot Manager for storage.
    """
    logger.info(f"Received transcription for meeting {request.meeting_id}")
    
    try:
        # Forward to Bot Manager API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BOT_MANAGER_URL}/transcription",
                json=request.dict(),
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"Error from Bot Manager API: {response.status_code} - {response.text}")
                raise HTTPException(status_code=500, detail="Failed to store transcription")
            
            return {"status": "success", "message": "Transcription processed"}
    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to communicate with Bot Manager: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/transcript/{user_id}/{meeting_id}")
async def get_transcript(user_id: str, meeting_id: str):
    """
    Retrieve transcript from the Bot Manager API
    """
    logger.info(f"Retrieving transcript for user {user_id}, meeting {meeting_id}")
    
    try:
        # Get from Bot Manager API
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BOT_MANAGER_URL}/transcript/{user_id}/{meeting_id}",
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"Error from Bot Manager API: {response.status_code} - {response.text}")
                if response.status_code == 404:
                    raise HTTPException(status_code=404, detail="Transcript not found")
                elif response.status_code == 403:
                    raise HTTPException(status_code=403, detail="Access denied")
                else:
                    raise HTTPException(status_code=500, detail="Failed to retrieve transcript")
            
            return response.json()
    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to communicate with Bot Manager: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True) 