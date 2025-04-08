from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, Depends, Header, Security, status
import json
import logging
import uuid
import os
import asyncio
from datetime import datetime
import redis.asyncio as redis
from sqlalchemy import select, and_, func, distinct, text
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from typing import Optional, List
from pydantic import ValidationError

from shared_models.database import get_db, init_db
from shared_models.models import APIToken, User, Meeting, Transcription
from shared_models.schemas import (
    TranscriptionSegment, 
    HealthResponse, 
    ErrorResponse,
    MeetingResponse,
    MeetingListResponse,
    TranscriptionResponse,
    TranscriptionData,
    TranscriptionRequest,
    Platform
)
from filters import TranscriptionFilter

app = FastAPI(
    title="Transcription Collector",
    description="Collects and stores transcriptions from WhisperLive instances."
)

# Configure logging
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("transcription_collector")

# Security - API Key auth
API_KEY_NAME = "X-API-Key"  # Standardize header name
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_current_user(api_key: str = Security(api_key_header),
                           db: AsyncSession = Depends(get_db)) -> User:
    """Dependency to verify X-API-Key and return the associated User."""
    if not api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing API token")
    
    # Find the token in the database
    result = await db.execute(
        select(APIToken, User)
        .join(User, APIToken.user_id == User.id)
        .where(APIToken.token == api_key)
    )
    token_user = result.first()
    
    if not token_user:
        logger.warning(f"Invalid API token provided: {api_key[:10]}...")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API token"
        )
    
    _token_obj, user_obj = token_user
    return user_obj

# Redis connection
redis_client = None

# Initialize transcription filter
transcription_filter = TranscriptionFilter()

@app.on_event("startup")
async def startup():
    global redis_client
    
    # Initialize Redis connection
    redis_host = os.environ.get("REDIS_HOST", "redis")
    redis_port = int(os.environ.get("REDIS_PORT", "6379"))
    logger.info(f"Connecting to Redis at {redis_host}:{redis_port}")
    
    redis_client = redis.Redis(
        host=redis_host,
        port=redis_port,
        db=0,
        decode_responses=True
    )
    
    # Initialize database connection
    await init_db()
    logger.info("Database initialized.")

@app.on_event("shutdown")
async def shutdown():
    # await disconnect_db() # Use Session context manager or engine.dispose()
    if redis_client:
        await redis_client.close()
    logger.info("Application shutting down, connections closed")

@app.websocket("/collector")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Generate unique server ID for this connection
    server_id = str(uuid.uuid4())
    logger.info(f"WhisperLive server {server_id} connected")
    
    try:
        while True:
            data = await websocket.receive_text()
            # First try to parse as TranscriptionData (meeting_id based)
            try:
                # Assume bots send TranscriptionData with internal meeting_id
                transcription_data = TranscriptionData.parse_raw(data)
                logger.info(f"Received TranscriptionData for meeting {transcription_data.meeting_id}")
                # Process using internal meeting ID
                await process_transcription(transcription_data, server_id)
                
            # --- Improved Error Handling --- 
            except (json.JSONDecodeError, ValidationError) as parse_error:
                # If parsing as TranscriptionData fails, log and try TranscriptionRequest
                logger.warning(f"Failed to parse incoming WebSocket data as TranscriptionData for server {server_id}: {parse_error}. Data: {data[:200]}")
                # Optionally, send error back to websocket
                try:
                    await websocket.send_json({"status": "error", "message": f"Invalid data format: {parse_error}"})
                except Exception as ws_send_err:
                    logger.error(f"Failed to send parse error to WebSocket {server_id}: {ws_send_err}")
            except Exception as data_process_err: # Catch errors from process_transcription
                logger.error(f"Error during process_transcription for server {server_id}: {data_process_err}", exc_info=True)
                try:
                    await websocket.send_json({"status": "error", "message": f"Processing error: {str(data_process_err)}"})
                except Exception as ws_send_err:
                    logger.error(f"Failed to send processing error to WebSocket {server_id}: {ws_send_err}")
                    
    except WebSocketDisconnect:
        logger.info(f"WhisperLive server {server_id} disconnected")
    except Exception as e:
        logger.error(f"Unhandled error in websocket connection with server {server_id}: {e}", exc_info=True)
        # Attempt to close gracefully if possible
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass # Ignore errors during close after another error

async def process_transcription(data: TranscriptionData, server_id: str):
    """Process incoming transcription data (with internal meeting_id) from WhisperLive."""
    meeting_id = data.meeting_id
    segments = data.segments
    
    if not meeting_id:
        logger.error(f"Received TranscriptionData without meeting_id from server {server_id}")
        return

    # Enhanced logging
    logger.info(f"Processing {len(segments)} segments for meeting_id={meeting_id} from server {server_id}")
    
    # Log a sample of the first segment if available
    if segments and len(segments) > 0:
        sample_segment = segments[0]
        logger.info(f"Sample segment for meeting {meeting_id}: start={sample_segment.start_time}, end={sample_segment.end_time}, text='{sample_segment.text[:50]}...' if len(sample_segment.text) > 50 else sample_segment.text")
    
    async with get_db() as db:
        # Check if meeting exists (optional, depends on whether bot guarantees existence)
        meeting = await db.get(Meeting, meeting_id)
        if not meeting:
            logger.warning(f"Meeting with id={meeting_id} not found. Cannot store segments.")
            return
        
        logger.info(f"Found meeting record: id={meeting.id}, platform={meeting.platform}, url={meeting.meeting_url}")

        new_segments_to_store = []
        processed_count = 0
        filtered_count = 0

        for segment in segments:
            if not segment.text or segment.start_time is None or segment.end_time is None:
                logger.debug(f"Skipping segment with missing data for meeting {meeting_id}")
                continue
            
            # Redis key for deduplication (internal meeting ID is sufficient)
            segment_key = f"segment:{meeting_id}:{segment.start_time:.3f}:{segment.end_time:.3f}"
            exists = await redis_client.get(segment_key)

            if not exists:
                await redis_client.setex(segment_key, 300, "processed") # Simple flag is enough
                
                if transcription_filter.filter_segment(segment.text):
                    # Use simplified function to create ORM object
                    new_transcription = create_transcription_object(
                        meeting_id=meeting_id,
                        start=segment.start_time,
                        end=segment.end_time,
                        text=segment.text,
                        language=segment.language
                    )
                    new_segments_to_store.append(new_transcription)
                    processed_count += 1
                else:
                    filtered_count += 1
                    logger.debug(f"Filtered out segment for meeting {meeting_id}: '{segment.text}'")
            else:
                logger.debug(f"Skipping duplicate segment for meeting {meeting_id} based on Redis key: {segment_key}")
        
        if new_segments_to_store:
            try:
                db.add_all(new_segments_to_store)
                await db.commit()
                logger.info(f"Stored {processed_count} new segments (filtered {filtered_count}) for meeting {meeting_id}")
            except Exception as e:
                await db.rollback()
                logger.error(f"Error storing batch of segments for meeting {meeting_id}: {e}", exc_info=True)
        else:
            logger.info(f"No new, non-duplicate, informative segments to store for meeting {meeting_id}")

# Simplified function - assumes meeting_id is valid
def create_transcription_object(meeting_id: int, start: float, end: float, text: str, language: Optional[str]) -> Transcription:
    """Creates a Transcription ORM object without adding/committing."""
    return Transcription(
        meeting_id=meeting_id,
        start_time=start,
        end_time=end,
        text=text,
        language=language,
        created_at=datetime.utcnow()
    )

@app.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check endpoint"""
    redis_status = "healthy"
    db_status = "healthy"
    
    try:
        await redis_client.ping()
    except Exception as e:
        redis_status = f"unhealthy: {str(e)}"
    
    try:
        # Use the injected session 'db'
        await db.execute(text("SELECT 1")) 
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    return HealthResponse(
        status="healthy" if redis_status == "healthy" and db_status == "healthy" else "unhealthy",
        redis=redis_status,
        database=db_status,
        timestamp=datetime.now().isoformat()
    )

@app.get("/meetings", 
         response_model=MeetingListResponse,
         summary="Get list of all meetings for the current user",
         dependencies=[Depends(get_current_user)])
async def get_meetings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Returns a list of all meetings initiated by the authenticated user."""
    stmt = select(Meeting).where(Meeting.user_id == current_user.id).order_by(Meeting.created_at.desc())
    result = await db.execute(stmt)
    meetings = result.scalars().all()
    return MeetingListResponse(meetings=[MeetingResponse.from_orm(m) for m in meetings])
    
@app.get("/transcripts/{platform}/{native_meeting_id}",
         response_model=TranscriptionResponse,
         summary="Get transcript for a specific meeting by platform and native ID",
         dependencies=[Depends(get_current_user)])
async def get_transcript_by_native_id(
    platform: Platform,
    native_meeting_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Retrieves the meeting details and transcript segments for a meeting specified by its platform and native ID.
    Finds the *latest* matching meeting record for the user.
    """
    logger.info(f"User {current_user.id} requested transcript for {platform.value} / {native_meeting_id}")

    # 1. Find the latest meeting matching platform and native ID for the user
    stmt_meeting = select(Meeting).where(
                Meeting.user_id == current_user.id,
        Meeting.platform == platform.value,
        Meeting.platform_specific_id == native_meeting_id
    ).order_by(Meeting.created_at.desc())

    result_meeting = await db.execute(stmt_meeting)
    meeting = result_meeting.scalars().first()
    
    if not meeting:
        logger.warning(f"No meeting found for user {current_user.id}, platform '{platform.value}', native ID '{native_meeting_id}'")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting not found for platform {platform.value} and ID {native_meeting_id}"
        )

    logger.info(f"Found meeting record ID {meeting.id} for transcript request.")
    internal_meeting_id = meeting.id

    # 2. Fetch transcript segments for the found internal meeting ID
    stmt_transcripts = select(Transcription).where(
        Transcription.meeting_id == internal_meeting_id
    ).order_by(Transcription.start_time)

    result_transcripts = await db.execute(stmt_transcripts)
    segments = result_transcripts.scalars().all()
    logger.info(f"Retrieved {len(segments)} segments for meeting {internal_meeting_id}")

    # 3. Construct the response using the found meeting and segments
    # Map ORM objects to Pydantic schemas
    meeting_details = MeetingResponse.from_orm(meeting)
    segment_details = [TranscriptionSegment.from_orm(s) for s in segments]

    # Combine into the final response model
    response_data = meeting_details.dict() # Get meeting data as dict
    response_data["segments"] = segment_details # Add segments list

    return TranscriptionResponse(**response_data)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=False,
        log_level="info"
    ) 