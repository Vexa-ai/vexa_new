import sqlalchemy
from sqlalchemy import (Column, String, Text, Integer, DateTime, Float, ForeignKey)
from sqlalchemy.sql import func
from sqlalchemy.orm import declarative_base
from datetime import datetime # Needed for Transcription model default

# Define the base class for declarative models
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True) # Added index=True
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(100))
    image_url = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

class APIToken(Base):
    __tablename__ = "api_tokens"
    id = Column(Integer, primary_key=True, index=True) # Added index=True
    token = Column(String(255), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    # user = relationship("User", back_populates="tokens") # Define relationship if needed

class Transcription(Base):
    __tablename__ = "transcriptions"
    id = Column(Integer, primary_key=True, index=True)
    client_uid = Column(String(255), index=True) # Example length, adjust as needed
    server_id = Column(String(255)) # Example length, adjust as needed
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    text = Column(Text, nullable=False)
    platform = Column(String(100))
    meeting_url = Column(Text)
    token = Column(String(255)) # Corresponds to APIToken? Or a different token? Indexed?
    language = Column(String(10)) # e.g., 'en', 'es'
    created_at = Column(DateTime, default=datetime.utcnow) # Use default instead of server_default if app handles timestamp

    # Potential relationships (uncomment and define if needed)
    # user_id = Column(Integer, ForeignKey("users.id")) # If linked to a user
    # meeting_id = Column(Integer, ForeignKey("meetings.id")) # If you create a Meeting model

# Example of a Meeting model if needed:
# class Meeting(Base):
#     __tablename__ = "meetings"
#     id = Column(Integer, primary_key=True, index=True)
#     platform = Column(String(100), nullable=False)
#     meeting_url = Column(Text, unique=True, nullable=False)
#     # Add created_at, updated_at etc. 