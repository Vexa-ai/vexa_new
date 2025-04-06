import os
import logging
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import create_engine # For sync engine if needed for migrations later

# Import Base from models within the same package
# Ensure models are imported somewhere before init_db is called so Base is populated.
from .models import Base 

logger = logging.getLogger("shared_models.database")

# --- Database Configuration --- 
DB_HOST = os.environ.get("DB_HOST", "postgres")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "vexa")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
DATABASE_URL_SYNC = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# --- SQLAlchemy Async Engine & Session --- 
# Use pool settings appropriate for async connections
engine = create_async_engine(
    DATABASE_URL, 
    echo=os.environ.get("LOG_LEVEL", "INFO").upper() == "DEBUG",
    pool_size=10, # Example pool size
    max_overflow=20 # Example overflow
)
async_session_local = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# --- Sync Engine (Optional, for Alembic) ---
# sync_engine = create_engine(DATABASE_URL_SYNC)

# --- FastAPI Dependency --- 
async def get_db() -> AsyncSession:
    """FastAPI dependency to get an async database session."""
    async with async_session_local() as session:
        try:
            yield session
        finally:
            # Ensure session is closed, though context manager should handle it
            await session.close()

# --- Initialization Function --- 
async def init_db():
    """Creates database tables based on shared models' metadata."""
    logger.info(f"Initializing database tables at {DB_HOST}:{DB_PORT}/{DB_NAME}")
    try:
        async with engine.begin() as conn:
            # This relies on all SQLAlchemy models being imported 
            # somewhere before this runs, so Base.metadata is populated.
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables checked/created successfully.")
    except Exception as e:
        logger.error(f"Error initializing database tables: {e}", exc_info=True)
        raise 