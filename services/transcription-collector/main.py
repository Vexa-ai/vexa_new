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
from typing import Optional, List, Dict
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
    Platform,
    WhisperLiveData
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
async def websocket_endpoint(websocket: WebSocket, db: AsyncSession = Depends(get_db)):
    await websocket.accept()
    connection_id = str(uuid.uuid4()) # Unique ID for this connection instance
    logger.info(f"WebSocket connection {connection_id} accepted.")

    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"[{connection_id}] RAW Data Received: {data}") # Log raw data

            try:
                # Attempt to parse the message using the combined WhisperLiveData schema
                whisper_data = WhisperLiveData.parse_raw(data)
                logger.info(f"[{connection_id}] Parsed WhisperLiveData: platform={whisper_data.platform.value}, native_id={whisper_data.meeting_id}, token={whisper_data.token[:5]}..., segments={len(whisper_data.segments)}")

                # 1. Validate Token and Get User
                try:
                    user = await get_user_by_token(whisper_data.token, db)
                    if not user: raise ValueError("User not found for token") # Should be handled by HTTPException in helper
                    logger.info(f"[{connection_id}] Token validated for user {user.id}")
                except HTTPException as auth_exc:
                    logger.warning(f"[{connection_id}] Auth failed for incoming data: {auth_exc.detail}")
                    # Decide if we close connection or just skip processing this batch
                    # Closing might be safer if auth fails.
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=f"Authentication Failed: {auth_exc.detail}")
                    return # Exit loop and close

                # 2. Find Internal Meeting ID
                stmt_meeting = select(Meeting).where(
                    Meeting.user_id == user.id,
                    Meeting.platform == whisper_data.platform.value,
                    Meeting.platform_specific_id == whisper_data.meeting_id # Match native ID from message
                ).order_by(Meeting.created_at.desc())

                result_meeting = await db.execute(stmt_meeting)
                meeting = result_meeting.scalars().first()

                if not meeting:
                    logger.warning(f"[{connection_id}] Meeting lookup failed: No meeting found for user {user.id}, platform '{whisper_data.platform.value}', native ID '{whisper_data.meeting_id}'")
                    # Decide whether to close or just log and skip processing
                    # Sending error back might cause issues if WhisperLive doesn't expect it
                    continue # Skip processing this message if meeting not found

                internal_meeting_id = meeting.id
                logger.info(f"[{connection_id}] Associated internal meeting ID: {internal_meeting_id}")

                # 3. Process Segments if meeting found
                if whisper_data.segments: # Check if there are segments in this message
                    await process_transcription(
                        internal_meeting_id=internal_meeting_id,
                        segments=whisper_data.segments,
                        server_id=connection_id, # Pass connection ID for logging
                        db=db # <<< Pass the db session from the endpoint dependency
                    )
                else:
                     logger.info(f"[{connection_id}] Received WhisperLiveData message for meeting {internal_meeting_id} with no segments.")

            except (json.JSONDecodeError, ValidationError) as parse_error:
                logger.warning(f"[{connection_id}] Failed to parse WhisperLiveData: {parse_error}. Data: {data[:500]}...") # Log more data on error
                # Don't close connection for parse errors, just log and wait for next message
                # Optionally send error back if WhisperLive client handles it:
                # try:
                #     await websocket.send_json({"status": "error", "message": f"Invalid data format: {parse_error}"})
                # except Exception: pass
            except Exception as process_err:
                # Catch errors during token validation or DB lookup *after* parsing
                logger.error(f"[{connection_id}] Error processing WhisperLiveData for native_id {whisper_data.meeting_id if 'whisper_data' in locals() else 'unknown'}: {process_err}", exc_info=True)
                # Decide if connection should be closed on processing errors

    except WebSocketDisconnect:
        logger.info(f"WebSocket connection {connection_id} disconnected.")
    except Exception as e:
        logger.error(f"Unhandled error in websocket connection {connection_id}: {e}", exc_info=True)
        # Attempt to close gracefully if possible
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass # Ignore errors during close after another error
    finally:
        # No connection-specific context to clean up anymore
        logger.info(f"WebSocket connection {connection_id} handler finished.")

# MODIFY process_transcription signature to accept db session
async def process_transcription(internal_meeting_id: int, segments: List[TranscriptionSegment], server_id: str, db: AsyncSession):
    """Process incoming transcription segments for a validated internal meeting ID."""
    # meeting_id is now passed directly
    # segments are passed directly
    # db session is now passed directly
    
    if not internal_meeting_id:
        logger.error(f"[{server_id}] process_transcription called without internal_meeting_id")
        return
    if not segments:
        logger.info(f"[{server_id}] process_transcription called with no segments for meeting {internal_meeting_id}. Nothing to process.")
        return

    # Enhanced logging
    logger.info(f"[{server_id}] Processing {len(segments)} segments for internal_meeting_id={internal_meeting_id}")
    
    # Log a sample of the first segment if available
    if segments: # Check if segments list is not empty
        sample_segment = segments[0]
        logger.info(f"[{server_id}] Sample segment for meeting {internal_meeting_id}: start={sample_segment.start_time}, end={sample_segment.end_time}, text='{sample_segment.text[:50]}...' if len(sample_segment.text) > 50 else sample_segment.text")
    else:
        logger.info(f"[{server_id}] Received empty segment list for meeting {internal_meeting_id}")
    
    # REMOVE async with get_db(), use passed-in db directly
    # async with get_db() as db:
    try: # Add try/except block for operations using the passed db session
        # Check if meeting exists (still a good safety check)
        meeting = await db.get(Meeting, internal_meeting_id)
        if not meeting:
            logger.warning(f"[{server_id}] Meeting with internal id={internal_meeting_id} not found. Cannot store segments.")
            return
        
        logger.info(f"[{server_id}] Found meeting record: id={meeting.id}, platform={meeting.platform}, native_id={meeting.platform_specific_id}")

        new_segments_to_store = []
        processed_count = 0
        filtered_count = 0

        for segment in segments:
            if not segment.text or segment.start_time is None or segment.end_time is None:
                logger.debug(f"[{server_id}] Skipping segment with missing data for meeting {internal_meeting_id}")
                continue
            
            # Redis key for deduplication uses internal meeting ID
            segment_key = f"segment:{internal_meeting_id}:{segment.start_time:.3f}:{segment.end_time:.3f}"
            exists = await redis_client.get(segment_key)

            if not exists:
                await redis_client.setex(segment_key, 300, "processed") # Simple flag is enough
                
                if transcription_filter.filter_segment(segment.text, language=(segment.language or 'en')):
                    new_transcription = create_transcription_object(
                        meeting_id=internal_meeting_id,
                        start=segment.start_time,
                        end=segment.end_time,
                        text=segment.text,
                        language=segment.language
                    )
                    new_segments_to_store.append(new_transcription)
                    processed_count += 1
                else:
                    filtered_count += 1
                    logger.debug(f"[{server_id}] Filtered out segment for meeting {internal_meeting_id}: '{segment.text}'")
            else:
                logger.debug(f"[{server_id}] Skipping duplicate segment for meeting {internal_meeting_id} based on Redis key: {segment_key}")
        
        if new_segments_to_store:
            # Use the passed-in db session
            db.add_all(new_segments_to_store)
            await db.commit()
            logger.info(f"[{server_id}] Stored {processed_count} new segments (filtered {filtered_count}) for meeting {internal_meeting_id}")
        else:
            logger.info(f"[{server_id}] No new, non-duplicate, informative segments to store for meeting {internal_meeting_id}")

    except Exception as e:
        # Handle potential exceptions during DB operations with the passed session
        logger.error(f"[{server_id}] Error during database operation in process_transcription for meeting {internal_meeting_id}: {e}", exc_info=True)
        try:
            await db.rollback() # Rollback the passed-in session
        except Exception as rb_err:
            logger.error(f"[{server_id}] Failed to rollback database session: {rb_err}")
        # Re-raising might be appropriate depending on desired error handling in websocket_endpoint
        # raise e 

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

# ADD Helper for token validation (or ensure it exists in an auth.py)
async def get_user_by_token(token: str, db: AsyncSession) -> Optional[User]:
    """Validates an API token and returns the associated User or raises HTTPException."""
    if not token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing API token")
    
    result = await db.execute(
        select(User).join(APIToken).where(APIToken.token == token)
    )
    user = result.scalars().first()
    
    if not user:
        logger.warning(f"Invalid API token provided in WebSocket handshake: {token[:5]}...")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API token"
        )
    return user

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=False,
        log_level="info"
    ) 