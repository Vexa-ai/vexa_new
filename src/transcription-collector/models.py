from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

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
    token: Optional[str] = None
    language: Optional[str] = None

class TranscriptionDB(TranscriptionCreate):
    id: int
    created_at: datetime

class TranscriptionResponse(BaseModel):
    id: int
    client_uid: str
    start_time: float
    end_time: float
    text: str
    platform: Optional[str] = None
    meeting_url: Optional[str] = None
    token: Optional[str] = None
    created_at: Optional[str] = None

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
    timestamp: str

class ErrorResponse(BaseModel):
    error: str

class Meeting(BaseModel):
    platform: str
    meeting_url: str

class MeetingListResponse(BaseModel):
    meetings: List[Meeting] 