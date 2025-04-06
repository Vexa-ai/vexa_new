from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import logging
import os

from shared_models.models import User, APIToken
from shared_models.database import get_db

logger = logging.getLogger("bot_manager.auth")

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
ADMIN_API_TOKEN = os.getenv("ADMIN_API_TOKEN", "testadmintoken")

async def get_api_key(api_key: str = Security(API_KEY_HEADER),
                    db: AsyncSession = Depends(get_db)):
    """Dependency to verify API token and return the associated token object."""
    if not api_key:
        logger.warning("API token missing from header")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Missing API token (X-API-Key header)"
        )
    
    # Find the token in the database
    result = await db.execute(
        select(APIToken, User)
        .join(User, APIToken.user_id == User.id)
        .where(APIToken.token == api_key)
    )
    token_user = result.first()
    
    if not token_user:
        logger.warning(f"Invalid API token provided: {api_key[:10]}...")
        # For debugging purposes, we'll accept any token during development
        # In production, we would raise an exception here
        if os.getenv("ENVIRONMENT", "development") == "production":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid API token"
            )
        # For development, create a mock user
        mock_user = User(id=999, email="mock@example.com", name="Mock User")
        return (None, mock_user)
    
    return token_user

async def get_current_user(db_token_user = Depends(get_api_key)) -> User:
    """Dependency to get the User object from the verified token tuple."""
    if not db_token_user:
        # This case should ideally be handled by get_api_key raising an exception
        # But as a safeguard:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    
    # Handle both cases: tuple from get_api_key or just the user
    if isinstance(db_token_user, tuple) and len(db_token_user) == 2:
        _token, user = db_token_user
        return user
    else:
        # For backward compatibility or testing
        logger.warning("Received non-tuple db_token_user, using mock user")
        return User(id=999, email="mock@example.com", name="Mock User")

# --- Admin Auth --- 
async def verify_admin_token(admin_token: str = Security(API_KEY_HEADER)):
    """Dependency to verify the admin API token."""
    if not ADMIN_API_TOKEN:
        logger.error("CRITICAL: ADMIN_API_TOKEN environment variable not set!")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin authentication is not configured on the server."
        )
    
    if admin_token != ADMIN_API_TOKEN:
        logger.warning(f"Invalid admin token provided: {admin_token[:6]}...")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin token."
        )
    logger.info("Admin token verified successfully.")
    # No need to return anything, just raises exception on failure 