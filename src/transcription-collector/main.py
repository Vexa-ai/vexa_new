from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import json
import logging
import uuid
import os
import asyncio
from datetime import datetime
import redis.asyncio as redis
import asyncpg

from filters import TranscriptionFilter

app = FastAPI(title="Transcription Collector")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("transcription_collector")

# Redis and PostgreSQL connections
redis_client = None
db_pool = None

# Initialize transcription filter
transcription_filter = TranscriptionFilter()

@app.on_event("startup")
async def startup():
    global redis_client, db_pool
    
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
    
    # Initialize database connection pool
    db_host = os.environ.get("DB_HOST", "postgres")
    db_port = int(os.environ.get("DB_PORT", "5432"))
    db_name = os.environ.get("DB_NAME", "vexa")
    db_user = os.environ.get("DB_USER", "postgres")
    db_password = os.environ.get("DB_PASSWORD", "postgres")
    
    logger.info(f"Connecting to PostgreSQL at {db_host}:{db_port}/{db_name}")
    
    try:
        db_pool = await asyncpg.create_pool(
            user=db_user,
            password=db_password,
            database=db_name,
            host=db_host,
            port=db_port
        )
        
        # Create tables if they don't exist
        async with db_pool.acquire() as conn:
            await conn.execute('''
            CREATE TABLE IF NOT EXISTS transcriptions (
                id SERIAL PRIMARY KEY,
                client_uid VARCHAR(50) NOT NULL,
                server_id VARCHAR(50) NOT NULL,
                start_time DECIMAL(10,3) NOT NULL,
                end_time DECIMAL(10,3) NOT NULL,
                text TEXT NOT NULL,
                language VARCHAR(10),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(client_uid, start_time, end_time)
            )
            ''')
        logger.info("Database initialization complete")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise e

@app.on_event("shutdown")
async def shutdown():
    if db_pool:
        await db_pool.close()
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
            await process_transcription(json.loads(data), server_id)
    except WebSocketDisconnect:
        logger.info(f"Server {server_id} disconnected")
    except Exception as e:
        logger.error(f"Error in websocket connection with server {server_id}: {e}")

async def process_transcription(data, server_id):
    """Process incoming transcription data"""
    client_uid = data.get("uid")
    segments = data.get("segments", [])
    
    if not client_uid or not segments:
        return
    
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
            "completed": completed,
            "timestamp": datetime.now().isoformat()
        })
        
        # For completed segments, store in database if informative and set short expiration in Redis
        if completed:
            if transcription_filter.filter_segment(text):
                await store_completed_segment(client_uid, server_id, start, end, text)
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

async def store_completed_segment(client_uid, server_id, start, end, text):
    """Store completed segment to database"""
    try:
        async with db_pool.acquire() as conn:
            await conn.execute('''
            INSERT INTO transcriptions(client_uid, server_id, start_time, end_time, text)
            VALUES($1, $2, $3, $4, $5)
            ON CONFLICT(client_uid, start_time, end_time) DO NOTHING
            ''', client_uid, server_id, start, end, text)
            logger.info(f"Stored completed segment for client {client_uid}: {start}-{end}, text: '{text}'")
    except Exception as e:
        logger.error(f"Error storing segment: {e}")

@app.get("/health")
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
        async with db_pool.acquire() as conn:
            await conn.execute("SELECT 1")
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    return {
        "status": "healthy" if redis_status == "healthy" and db_status == "healthy" else "unhealthy",
        "redis": redis_status,
        "database": db_status,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/stats")
async def get_stats():
    """Get statistics about stored transcriptions"""
    stats = {}
    
    try:
        async with db_pool.acquire() as conn:
            # Total segments
            stats["total_segments"] = await conn.fetchval("SELECT COUNT(*) FROM transcriptions")
            
            # Segments per client
            client_stats = await conn.fetch(
                "SELECT client_uid, COUNT(*) as segment_count FROM transcriptions GROUP BY client_uid"
            )
            stats["clients"] = {row["client_uid"]: row["segment_count"] for row in client_stats}
            
            # Recent segments
            recent_segments = await conn.fetch(
                "SELECT client_uid, text, start_time, end_time, created_at FROM transcriptions " +
                "ORDER BY created_at DESC LIMIT 5"
            )
            stats["recent_segments"] = [dict(row) for row in recent_segments]
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        stats["error"] = str(e)
    
    return stats

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=False,
        log_level="info"
    ) 