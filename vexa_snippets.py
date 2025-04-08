"""Vexa API Client - Minimal Usage Snippets"""
from vexa_client import VexaClient

# --- Client Initialization ---
# User client
client = VexaClient(
    base_url="http://localhost:8056",
    api_key="your-user-api-key"
)

# Admin client 
admin_client = VexaClient(
    base_url="http://localhost:8056",
    admin_key="supersecretadmintoken"  # From docker-compose.yml
)

# --- Admin Operations ---
# Create user
new_user = admin_client.create_user(email="user@example.com", name="New User")
user_id = new_user['id']

# List users
users = admin_client.list_users(limit=10)

# Create token
token_info = admin_client.create_token(user_id=user_id)
api_key = token_info['token']

# --- User Operations ---
# List meetings
meetings = client.get_meetings()

# Request bot
meeting_info = client.request_bot(
    platform="google_meet",
    meeting_url="https://meet.google.com/xyz-abcd-123",
    bot_name="MyBot"
)
meeting_id = meeting_info['id']

# Get transcript
transcript = client.get_transcript(meeting_id=meeting_id)
segments = transcript.get('segments', [])

# Stop bot
stop_info = client.stop_bot(meeting_id=meeting_id) 