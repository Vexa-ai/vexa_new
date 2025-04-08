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

async def get_api_key(api_key: str = Security(API_KEY_HEADER),
                    db: AsyncSession = Depends(get_db)) -> tuple:
    """Dependency to verify X-API-Key and return the (APIToken, User) tuple."""
    if not api_key:
        logger.warning("API token missing from header")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Missing API token (X-API-Key header)"
        )
    
    # Log the API key received for debugging
    logger.info(f"Received API key: {api_key[:5]}...")
    
    # Find the token in the database
    result = await db.execute(
        select(APIToken, User)
        .join(User, APIToken.user_id == User.id)
        .where(APIToken.token == api_key)
    )
    token_user = result.first()
    
    if not token_user:
        logger.warning(f"Invalid API token provided: {api_key[:5]}...")
        # Do NOT return mock user in any environment
        # if os.getenv("ENVIRONMENT", "development") == "production":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API token"
        )
        # # For development, create a mock user
        # mock_user = User(id=999, email="mock@example.com", name="Mock User")
        # return (None, mock_user)
    
    return token_user # Return (APIToken, User) tuple

async def get_current_user(db_token_user: tuple = Depends(get_api_key)) -> User:
    """Dependency to get the User object from the verified (APIToken, User) tuple."""
    logger.info(f"get_current_user received: {type(db_token_user)}")
    if db_token_user is None:
        logger.error("get_current_user received None from get_api_key")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        
    # Handle SQLAlchemy Row objects (from query result)
    if hasattr(db_token_user, "_mapping"):
        logger.info("Processing token_user as SQLAlchemy Row object")
        token = db_token_user[0]  # First item in the row should be the token
        user = db_token_user[1]   # Second item should be the user
        
        if not isinstance(user, User):
            logger.error(f"get_current_user: user is not a User instance, but {type(user)}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication error")
            
        logger.info(f"Successfully authenticated user ID: {user.id}, email: {user.email}")
        return user
    
    # Original tuple handling
    if not isinstance(db_token_user, tuple) or len(db_token_user) != 2:
        logger.error(f"get_current_user received invalid input from get_api_key: {type(db_token_user)}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    
    _token, user = db_token_user
    if not isinstance(user, User):
         logger.error(f"get_current_user did not receive a valid User object: {type(user)}")
         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication error")
         
    logger.info(f"Successfully authenticated user ID: {user.id}, email: {user.email}")
    return user

# --- Remove Admin Auth --- 
# async def verify_admin_token(admin_token: str = Security(API_KEY_HEADER)):
#    ... 