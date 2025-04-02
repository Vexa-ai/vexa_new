import os
import logging
import sqlalchemy
from sqlalchemy import (Column, String, Text, Integer, DateTime, Table, MetaData,
                        ForeignKey, create_engine)
from sqlalchemy.sql import func
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from databases import Database # Keep for potential raw queries if needed

# Configure logging
logger = logging.getLogger("bot_manager.database")

# --- Database Configuration from Environment Variables --- 
DB_HOST = os.environ.get("DB_HOST", "postgres")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "vexa")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
DATABASE_URL_SYNC = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# --- SQLAlchemy Setup (Async) --- 
engine = create_async_engine(DATABASE_URL, echo=os.environ.get("LOG_LEVEL") == "DEBUG")
async_session_local = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
Base = declarative_base()

# --- SQLAlchemy Setup (Sync for Alembic/Initial Creation) ---
sync_engine = create_engine(DATABASE_URL_SYNC)

# --- Models --- 
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(100))
    image_url = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

class APIToken(Base):
    __tablename__ = "api_tokens"
    id = Column(Integer, primary_key=True)
    token = Column(String(255), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    # user = relationship("User", back_populates="tokens") # Define relationship if needed

# --- Database Connection Functions --- 
async def get_db() -> AsyncSession:
    """FastAPI dependency to get an async database session."""
    async with async_session_local() as session:
        yield session

async def init_db():
    """Creates database tables based on models (use sync engine)."""
    logger.info(f"Initializing database tables at {DB_HOST}:{DB_PORT}/{DB_NAME}")
    try:
        # Using sync engine for table creation as it's simpler
        Base.metadata.create_all(bind=sync_engine)
        logger.info("Database tables checked/created successfully.")
    except Exception as e:
        logger.error(f"Error initializing database tables: {e}", exc_info=True)
        raise 