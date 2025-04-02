import logging
import secrets
import string
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import get_db, User, APIToken
from auth import verify_admin_token

logger = logging.getLogger("bot_manager.admin")
router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(verify_admin_token)] # Protect all admin routes
)

# --- Pydantic Models for Admin --- 
class UserCreate(BaseModel):
    email: EmailStr
    name: str | None = None
    image_url: str | None = None

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    name: str | None
    image_url: str | None
    created_at: str # Use string for simplicity

class TokenResponse(BaseModel):
    token: str
    user_id: int
    created_at: str

class UserDetailResponse(UserResponse):
    tokens: list[TokenResponse] = []

# --- Helper Functions --- 
def generate_secure_token(length=40):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for i in range(length))

# --- Admin Endpoints --- 
@router.post("/users", 
             response_model=UserResponse, 
             status_code=status.HTTP_201_CREATED,
             summary="Create a new user")
async def create_user(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    # Check if user already exists
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
    return UserResponse(
        id=db_user.id,
        email=db_user.email,
        name=db_user.name,
        image_url=db_user.image_url,
        created_at=str(db_user.created_at)
    )

@router.get("/users", 
            response_model=list[UserResponse],
            summary="List all users")
async def list_users(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).offset(skip).limit(limit))
    users = result.scalars().all()
    return [UserResponse(
        id=u.id, email=u.email, name=u.name, image_url=u.image_url, created_at=str(u.created_at)
    ) for u in users]

@router.post("/users/{user_id}/tokens", 
             response_model=TokenResponse,
             status_code=status.HTTP_201_CREATED,
             summary="Generate a new API token for a user")
async def create_token_for_user(user_id: int, db: AsyncSession = Depends(get_db)):
    # Check if user exists
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    token_value = generate_secure_token()
    db_token = APIToken(token=token_value, user_id=user_id)
    db.add(db_token)
    await db.commit()
    await db.refresh(db_token)
    logger.info(f"Admin created token for user {user_id} ({user.email})")
    return TokenResponse(
        token=db_token.token,
        user_id=db_token.user_id,
        created_at=str(db_token.created_at)
    )

# TODO: Add endpoints for GET /users/{id}, DELETE /users/{id}, DELETE /tokens/{token_value} 