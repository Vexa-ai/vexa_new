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
    return api_key

async def get_current_user(db_token_user: tuple = Depends(get_api_key)) -> User:
    """Dependency to get the User object from the verified token tuple."""
    if not db_token_user:
        # This case should ideally be handled by get_api_key raising an exception
        # But as a safeguard:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    _token, user = db_token_user
    return user

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