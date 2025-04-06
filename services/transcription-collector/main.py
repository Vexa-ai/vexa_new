from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, Depends, Header, Security
import json
import logging
import uuid
import os
import asyncio
from datetime import datetime
import redis.asyncio as redis
from sqlalchemy import select, and_, func, distinct, text
from fastapi.security.api_key import APIKeyHeader, APIKey

from database import database, connect_db, disconnect_db, TRANSCRIPTIONS_TABLE_NAME
from shared_models.schemas import (
    TranscriptionResponse, TranscriptsResponse, FullTranscript, HealthResponse, 
    ErrorResponse, TranscriptionSegment, MeetingListResponse, Meeting, TranscriptionCreate
)
from filters import TranscriptionFilter

app = FastAPI(title="Transcription Collector")

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("transcription_collector")

# Security - API Key auth
API_KEY_NAME = "X-API-Token"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    if not api_key_header:
        raise HTTPException(status_code=403, detail="Missing API token")
    return api_key_header

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
    await connect_db()

@app.on_event("shutdown")
async def shutdown():
    await disconnect_db()
    if redis_client:
        await redis_client.close()
    logger.info("Application shutting down, connections closed")

@app.websocket("/collector")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Generate unique server ID for this connection
    server_id = str(uuid.uuid4())
    logger.info(f"Server {server_id} connected")
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                await process_transcription(json.loads(data), server_id)
            except ValueError as ve:
                # Log validation errors and send back to client
                error_message = str(ve)
                logger.error(f"Validation error from server {server_id}: {error_message}")
                await websocket.send_json({
                    "status": "error",
                    "message": error_message
                })
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received from server {server_id}")
                await websocket.send_json({
                    "status": "error",
                    "message": "Invalid JSON format"
                })
            except Exception as e:
                # Log other errors
                logger.error(f"Error processing transcription from server {server_id}: {e}")
                await websocket.send_json({
                    "status": "error",
                    "message": f"Processing error: {str(e)}"
                })
    except WebSocketDisconnect:
        logger.info(f"Server {server_id} disconnected")
    except Exception as e:
        logger.error(f"Error in websocket connection with server {server_id}: {e}")

async def process_transcription(data, server_id):
    """Process incoming transcription data"""
    client_uid = data.get("uid")
    segments = data.get("segments", [])
    platform = data.get("platform")
    meeting_url = data.get("meeting_url")
    token = data.get("token")
    
    # Validate required fields
    if not client_uid or not segments:
        logger.error(f"Missing required fields: client_uid or segments")
        return
    
    if not platform or not meeting_url or not token:
        error_msg = f"ERROR: Missing critical fields for client {client_uid}: platform={platform}, meeting_url={meeting_url}, token={token}"
        logger.error(error_msg)
        # Raise error instead of defaulting to unknown
        raise ValueError(error_msg)
    
    logger.debug(f"Processing {len(segments)} segments from client {client_uid} via server {server_id}")
    
    for segment in segments:
        # Skip segments without timestamps or text
        if not all(k in segment for k in ["start", "end", "text"]):
            continue
        
        start = float(segment["start"])
        end = float(segment["end"])
        text = segment["text"]
        completed = segment.get("completed", False)
        
        # Create a key for Redis
        segment_key = f"segment:{client_uid}:{start}:{end}"
        
        # Store segment data in Redis
        segment_data = json.dumps({
            "client_uid": client_uid,
            "server_id": server_id,
            "start": start,
            "end": end,
            "text": text,
            "platform": platform,
            "meeting_url": meeting_url,
            "token": token,
            "completed": completed,
            "timestamp": datetime.now().isoformat()
        })
        
        # For completed segments, store in database if informative and set short expiration in Redis
        if completed:
            if transcription_filter.filter_segment(text):
                await store_completed_segment(client_uid, server_id, start, end, text, platform, meeting_url, token)
            else:
                logger.info(f"Filtered out non-informative segment: '{text}'")
            
            # Keep in Redis for 5 minutes for deduplication purposes (even non-informative ones)
            await redis_client.setex(segment_key, 300, segment_data)
        else:
            # For incomplete segments, store in Redis with longer expiry
            # Check if we already have this segment in Redis
            existing = await redis_client.get(segment_key)
            if existing:
                existing_data = json.loads(existing)
                # Only update if not already marked as completed
                if not existing_data.get("completed", False):
                    await redis_client.setex(segment_key, 1800, segment_data)  # 30 minutes expiry
            else:
                await redis_client.setex(segment_key, 1800, segment_data)  # 30 minutes expiry

async def store_completed_segment(client_uid, server_id, start, end, text, platform=None, meeting_url=None, token=None):
    """Store completed segment to database using the 'databases' library and table name."""
    try:
        # Ensure required fields have values
        if not platform or not meeting_url or not token:
            error_msg = f"ERROR: Cannot store segment with missing fields for client {client_uid}: platform={platform}, meeting_url={meeting_url}, token={token}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Manually create the insert query using the table name
        # NOTE: This relies on column names matching the Transcription model in shared_models
        query = f"""INSERT INTO {TRANSCRIPTIONS_TABLE_NAME} 
                     (client_uid, server_id, start_time, end_time, text, platform, meeting_url, token, created_at)
                     VALUES (:client_uid, :server_id, :start_time, :end_time, :text, :platform, :meeting_url, :token, :created_at)
                     ON CONFLICT DO NOTHING""" # Assumes a unique constraint exists
        
        values = {
            "client_uid": client_uid,
            "server_id": server_id,
            "start_time": start,
            "end_time": end,
            "text": text,
            "platform": platform,
            "meeting_url": meeting_url,
            "token": token,
            "created_at": datetime.utcnow() # Generate timestamp here
        }
        
        # Execute the query - Removed inner try/except
        await database.execute(query=query, values=values)
        logger.info(f"Stored completed segment for client {client_uid}: {start}-{end}, text: '{text}'")
                
    except Exception as e:
        logger.error(f"Error storing segment: {e}")
        raise # Re-raise the exception for FastAPI to handle

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    redis_status = "healthy"
    db_status = "healthy"
    
    try:
        # Check Redis connection
        await redis_client.ping()
    except Exception as e:
        redis_status = f"unhealthy: {str(e)}"
    
    try:
        # Check DB connection
        await database.execute("SELECT 1")
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    return HealthResponse(
        status="healthy" if redis_status == "healthy" and db_status == "healthy" else "unhealthy",
        redis=redis_status,
        database=db_status,
        timestamp=datetime.now().isoformat()
    )

@app.get("/stats")
async def get_stats():
    """Get statistics about stored transcriptions"""
    stats = {}
    
    try:
        # Total segments
        query = f"SELECT COUNT(*) FROM {TRANSCRIPTIONS_TABLE_NAME}"
        result = await database.fetch_val(query)
        stats["total_segments"] = result
            
        # Segments per client
        query = f"SELECT client_uid, COUNT(*) as count FROM {TRANSCRIPTIONS_TABLE_NAME} GROUP BY client_uid"
        result = await database.fetch_all(query)
        stats["segments_per_client"] = {row["client_uid"]: row["count"] for row in result}

        # Unique meetings (platform + meeting_url)
        query = f"SELECT DISTINCT platform, meeting_url FROM {TRANSCRIPTIONS_TABLE_NAME}"
        result = await database.fetch_all(query)
        stats["unique_meetings"] = len(result)

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        stats["error"] = str(e)
        
    return stats

@app.get("/meetings", response_model=MeetingListResponse)
async def get_meetings(
    token: APIKey = Depends(get_api_key)
):
    """List unique meetings stored in the database."""
    query = f"SELECT DISTINCT platform, meeting_url FROM {TRANSCRIPTIONS_TABLE_NAME}"
    try:
        results = await database.fetch_all(query)
        meetings = [Meeting(platform=row["platform"], meeting_url=row["meeting_url"]) for row in results]
        return MeetingListResponse(meetings=meetings)
    except Exception as e:
        logger.error(f"Error fetching meetings: {e}")
        raise HTTPException(status_code=500, detail="Error fetching meeting list")

@app.get("/meeting/transcript", response_model=FullTranscript)
async def get_meeting_transcript(
    platform: str = Query(..., description="Platform (e.g., google_meet)"),
    meeting_url: str = Query(..., description="Meeting URL"),
    token: APIKey = Depends(get_api_key)
):
    """Retrieve the full transcript for a specific meeting."""
    query = f"""SELECT client_uid, start_time, end_time, text, created_at
               FROM {TRANSCRIPTIONS_TABLE_NAME}
               WHERE platform = :platform AND meeting_url = :meeting_url
               ORDER BY start_time"""
    values = {"platform": platform, "meeting_url": meeting_url}
    
    try:
        results = await database.fetch_all(query=query, values=values)
        if not results:
            raise HTTPException(status_code=404, detail="Transcript not found for this meeting")
        
        segments = [
            TranscriptionSegment(
                client_uid=row["client_uid"],
                start_time=row["start_time"],
                end_time=row["end_time"],
                text=row["text"],
                timestamp=row["created_at"] # Assuming created_at is the segment timestamp
            )
            for row in results
        ]
        
        full_text = "\n".join(seg.text for seg in segments)
        
        # Extract other details from the first segment (assuming they are consistent)
        first_row = results[0]
        client_uid = first_row["client_uid"]
        # Need to fetch token associated with the meeting - how is this stored/related?
        # For now, returning None for token and sessions
        
        return FullTranscript(
            client_uid=client_uid,
            platform=platform,
            meeting_url=meeting_url,
            token=None, # How to get the original request token?
            sessions=None, # How are sessions defined?
            segments=segments,
            full_text=full_text
        )
    except HTTPException as e:
        raise e # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"Error fetching transcript for {platform} - {meeting_url}: {e}")
        raise HTTPException(status_code=500, detail="Error fetching transcript")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=False,
        log_level="info"
    ) 