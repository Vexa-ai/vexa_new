import logging
import secrets
import string
import os
from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List # Import List for response model

# Import shared models and schemas
from shared_models.models import User, APIToken, Base # Import Base for init_db
from shared_models.schemas import UserCreate, UserResponse, TokenResponse, UserDetailResponse # Import required schemas

# Database utilities (needs to be created)
from shared_models.database import get_db, init_db # New import

# Logging configuration
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("admin_api")

# App initialization
app = FastAPI(title="Vexa Admin API")

# Security - Reuse logic from bot-manager/auth.py for admin token verification
API_KEY_HEADER = APIKeyHeader(name="X-Admin-API-Key", auto_error=False) # Use a distinct header
ADMIN_API_TOKEN = os.getenv("ADMIN_API_TOKEN") # Read from environment

async def verify_admin_token(admin_api_key: str = Security(API_KEY_HEADER)):
    """Dependency to verify the admin API token."""
    if not ADMIN_API_TOKEN:
        logger.error("CRITICAL: ADMIN_API_TOKEN environment variable not set!")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin authentication is not configured on the server."
        )
    
    if not admin_api_key or admin_api_key != ADMIN_API_TOKEN:
        logger.warning(f"Invalid admin token provided.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing admin token."
        )
    logger.info("Admin token verified successfully.")
    # No need to return anything, just raises exception on failure 

# Router setup (all routes require admin token verification)
router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(verify_admin_token)]
)

# --- Helper Functions --- 
def generate_secure_token(length=40):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for i in range(length))

# --- Admin Endpoints (Copied and adapted from bot-manager/admin.py) --- 
@router.post("/users", 
             response_model=UserResponse, 
             status_code=status.HTTP_201_CREATED,
             summary="Create a new user")
async def create_user(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    existing_user = await db.execute(select(User).where(User.email == user_in.email))
    if existing_user.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, 
            detail="User with this email already exists"
        )
    db_user = User(**user_in.dict())
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    logger.info(f"Admin created user: {db_user.email} (ID: {db_user.id})")
    # Use UserResponse for consistency with schema definition (datetime object)
    return UserResponse.from_orm(db_user)

@router.get("/users", 
            response_model=List[UserResponse], # Use List import
            summary="List all users")
async def list_users(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).offset(skip).limit(limit))
    users = result.scalars().all()
    return [UserResponse.from_orm(u) for u in users]

@router.post("/users/{user_id}/tokens", 
             response_model=TokenResponse,
             status_code=status.HTTP_201_CREATED,
             summary="Generate a new API token for a user")
async def create_token_for_user(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    token_value = generate_secure_token()
    # Use the APIToken model from shared_models
    db_token = APIToken(token=token_value, user_id=user_id)
    db.add(db_token)
    await db.commit()
    await db.refresh(db_token)
    logger.info(f"Admin created token for user {user_id} ({user.email})")
    # Use TokenResponse for consistency with schema definition (datetime object)
    return TokenResponse.from_orm(db_token)

# TODO: Add endpoints for GET /users/{id}, DELETE /users/{id}, DELETE /tokens/{token_value}

# Include the router in the main app
app.include_router(router)

# Add startup event to initialize DB (if needed for this service)
@app.on_event("startup")
async def startup_event():
    logger.info("Starting up Admin API...")
    # Requires database_utils.py to be created in admin-api/app
    await init_db() 
    logger.info("Database initialized.")

# Root endpoint (optional)
@app.get("/")
async def root():
    return {"message": "Vexa Admin API"}
