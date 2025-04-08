# Vexa Client Snippets

## Initialize Clients

```python
# User client
client = VexaClient(base_url="http://localhost:8056", api_key="your-api-key")

# Admin client
admin_client = VexaClient(base_url="http://localhost:8056", admin_key="supersecretadmintoken")
```

## Admin Operations

### Create User
```python
new_user = admin_client.create_user(email="user@example.com", name="New User")
user_id = new_user['id']
```

### List Users
```python
users = admin_client.list_users(limit=10)
```

### Create API Token
```python
token_info = admin_client.create_token(user_id=1)
api_key = token_info['token']
```

## User Operations

### List Meetings
```python
meetings = client.get_meetings()
```

### Request Bot
```python
meeting_info = client.request_bot(
    platform="google_meet",
    meeting_url="https://meet.google.com/xyz-abcd-123"
)
meeting_id = meeting_info['id']
```

### Get Transcript
```python
transcript = client.get_transcript(meeting_id=1)
segments = transcript.get('segments', [])
```

### Stop Bot
```python
stop_info = client.stop_bot(meeting_id=1)
``` 