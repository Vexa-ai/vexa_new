import os
import logging
import sqlalchemy
from sqlalchemy.schema import Index
from databases import Database

# Configure logging
logger = logging.getLogger("transcription_collector.database")

# Database configuration from environment variables
DB_HOST = os.environ.get("DB_HOST", "postgres")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "vexa")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Database instance
database = Database(DATABASE_URL)

# SQLAlchemy metadata object
metadata = sqlalchemy.MetaData()

# Define table name (used in main.py queries)
TRANSCRIPTIONS_TABLE_NAME = "transcriptions"

# Connect to the database
async def connect_db():
    logger.info(f"Connecting to PostgreSQL at {DB_HOST}:{DB_PORT}/{DB_NAME}")
    try:
        await database.connect()
        logger.info("Database connection established")
        
        # NOTE: Table creation logic removed. Assumes tables are created elsewhere
        # (e.g., by bot-manager's init_db or Alembic migrations based on shared_models)
        # engine = sqlalchemy.create_engine(DATABASE_URL)
        # metadata.create_all(engine)
        # logger.info("Database tables created if they didn't exist")
        
        return True
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return False

# Disconnect from the database
async def disconnect_db():
    if database.is_connected:
        await database.disconnect()
        logger.info("Database connection closed") 