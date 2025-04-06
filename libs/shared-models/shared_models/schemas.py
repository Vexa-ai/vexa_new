from typing import List, Optional
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime

# --- Schemas from Admin API --- 

class UserBase(BaseModel): # Base for common user fields
    email: EmailStr
    name: Optional[str] = None
    image_url: Optional[str] = None

class UserCreate(UserBase):
    pass # Inherits all fields from UserBase

class UserResponse(UserBase):
    id: int
    created_at: datetime # Keep as datetime for internal use

    class Config:
        orm_mode = True # Compatibility with SQLAlchemy models

class TokenBase(BaseModel):
    user_id: int

class TokenCreate(TokenBase): # Not strictly needed if token generated internally
    pass

class TokenResponse(TokenBase):
    id: int # Assuming APIToken model has an ID
    token: str
    created_at: datetime

    class Config:
        orm_mode = True

class UserDetailResponse(UserResponse):
    tokens: List[TokenResponse] = []

# --- Schemas from Transcription Collector --- 

class SegmentBase(BaseModel):
    start_time: float
    end_time: float
    text: str

class TranscriptionSegment(SegmentBase):
    client_uid: str
    timestamp: Optional[datetime] = None

class TranscriptionCreate(SegmentBase):
    client_uid: str
    server_id: str
    platform: Optional[str] = None
    meeting_url: Optional[str] = None
    token: Optional[str] = None # API Token or other?
    language: Optional[str] = None

class TranscriptionDB(TranscriptionCreate):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True

class TranscriptionResponse(BaseModel):
    id: int
    client_uid: str
    start_time: float
    end_time: float
    text: str
    platform: Optional[str] = None
    meeting_url: Optional[str] = None
    token: Optional[str] = None
    created_at: datetime # Keep as datetime

    class Config:
        orm_mode = True

class TranscriptsResponse(BaseModel):
    total: int
    transcripts: List[TranscriptionResponse]

class FullTranscript(BaseModel):
    client_uid: Optional[str] = None
    platform: Optional[str] = None
    meeting_url: Optional[str] = None
    token: Optional[str] = None
    sessions: Optional[List[str]] = None
    segments: List[TranscriptionSegment]
    full_text: str

class HealthResponse(BaseModel):
    status: str
    redis: str
    database: str
    timestamp: datetime

class ErrorResponse(BaseModel):
    error: str

class Meeting(BaseModel):
    platform: str
    meeting_url: str

class MeetingListResponse(BaseModel):
    meetings: List[Meeting] 