import os
import logging
import sqlalchemy
from sqlalchemy import Column, String, Float, Text, Integer, DateTime, Table, MetaData
from sqlalchemy.sql import func
from databases import Database

# Configure logging
logger = logging.getLogger("transcription_collector.database")

# Database configuration from environment variables
DB_HOST = os.environ.get("DB_HOST", "postgres")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "vexa")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Database instance
database = Database(DATABASE_URL)

# SQLAlchemy metadata object
metadata = MetaData()

# Define transcriptions table
transcriptions = Table(
    "transcriptions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("client_uid", String(255), nullable=False),
    Column("server_id", String(50), nullable=False),
    Column("start_time", Float, nullable=False),
    Column("end_time", Float, nullable=False),
    Column("text", Text, nullable=False),
    Column("language", String(10)),
    Column("platform", String(50), nullable=False),
    Column("meeting_url", String(255), nullable=False),
    Column("token", String(255), nullable=False),
    Column("created_at", DateTime, server_default=func.now())
)

# Create a unique index on (client_uid, start_time, end_time)
Index = sqlalchemy.schema.Index(
    'uix_client_segment', 
    transcriptions.c.client_uid, 
    transcriptions.c.start_time, 
    transcriptions.c.end_time, 
    unique=True
)

# Connect to the database
async def connect_db():
    logger.info(f"Connecting to PostgreSQL at {DB_HOST}:{DB_PORT}/{DB_NAME}")
    try:
        await database.connect()
        logger.info("Database connection established")
        
        # Create tables if they don't exist
        engine = sqlalchemy.create_engine(DATABASE_URL)
        metadata.create_all(engine)
        logger.info("Database tables created if they didn't exist")
        
        return True
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return False

# Disconnect from the database
async def disconnect_db():
    if database.is_connected:
        await database.disconnect()
        logger.info("Database connection closed") 