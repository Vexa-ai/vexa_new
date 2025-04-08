import sys
import os
import uuid
import argparse
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import models - Assuming shared_models is installed as a package inside container
from shared_models.models import User, APIToken, Meeting, Base

# Argument parser
parser = argparse.ArgumentParser(description="Setup test data for Vexa")
parser.add_argument("--db-host", default=os.environ.get("DB_HOST", "localhost"), help="Database host")
args = parser.parse_args()

# Database connection
DB_HOST = args.db_host
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "vexa")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

print(f"Connecting to database at {DB_HOST}:{DB_PORT}/{DB_NAME}...")

# Create DB engine and session
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

# Create base tables if they don't exist (needed for fresh DB)
print("Ensuring tables exist...")
Base.metadata.create_all(bind=engine)
print("Tables checked/created.")

# Create test user
user = session.query(User).filter_by(email='test@example.com').first()
if not user:
    user = User(
        email='test@example.com',
        name='Test User',
        created_at=datetime.utcnow()
    )
    session.add(user)
    session.commit()
    print(f"Created user: {user.id}, {user.email}")
else:
    print(f"Using existing user: {user.id}, {user.email}")

# Create API token
token = session.query(APIToken).filter_by(user_id=user.id).first()
if not token:
    token = APIToken(
        token=str(uuid.uuid4()),
        user_id=user.id,
        created_at=datetime.utcnow()
    )
    session.add(token)
    session.commit()
    print(f"Created API token: {token.token}")
else:
    print(f"Using existing API token: {token.token}")

# Create test meeting
platform = "google_meet"
meeting_url = "https://meet.google.com/test-meeting-123" # Keep a generic test meeting

meeting = session.query(Meeting).filter_by(
    user_id=user.id,
    platform=platform,
    meeting_url=meeting_url
).first()

if not meeting:
    meeting = Meeting(
        user_id=user.id,
        platform=platform,
        meeting_url=meeting_url,
        status="requested", # Default status
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    session.add(meeting)
    session.commit()
    print(f"Created meeting: {meeting.id}, {platform}/{meeting_url}")
else:
    print(f"Using existing meeting: {meeting.id}, {platform}/{meeting_url}")

print("\nTEST DATA READY:")
print(f"User ID: {user.id}")
print(f"API Key: {token.token}")
print(f"Meeting ID: {meeting.id}")
print(f"Platform: {meeting.platform}")
print(f"Meeting URL: {meeting.meeting_url}") 