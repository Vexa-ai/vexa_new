from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import logging
import os

from database import get_db, User, APIToken

logger = logging.getLogger("bot_manager.auth")

API_KEY_NAME = "X-API-Token"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

ADMIN_API_TOKEN = os.environ.get("ADMIN_API_TOKEN")

async def get_api_key(api_key_header: str = Security(api_key_header)) -> str:
    """Dependency to extract API key from header."""
    if not api_key_header:
        logger.warning("API token missing from header")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Missing API token (X-API-Token header)"
        )
    return api_key_header

async def get_current_user(token: str = Depends(get_api_key),
                         db: AsyncSession = Depends(get_db)) -> User:
    """Dependency to verify API token and return the associated user."""
    logger.debug(f"Authenticating token: {token[:6]}...")
    
    query = (
        select(User)
        .join(APIToken, User.id == APIToken.user_id)
        .where(APIToken.token == token)
    )
    result = await db.execute(query)
    user = result.scalars().first()
    
    if user is None:
        logger.warning(f"Invalid API token provided: {token[:6]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid API token"
        )
    
    logger.info(f"Authenticated user {user.id} ({user.email}) via token {token[:6]}...")
    return user

# --- Admin Auth --- 
async def verify_admin_token(admin_token: str = Depends(get_api_key)):
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