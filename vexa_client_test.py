import requests
import os

# API key
api_key = "rOhvOLn85kowg0HjrD89R1rygHhMyHDAbyPjEFZS"
gateway_url = "http://localhost:8056"

# Test list meetings
print(f"\nTesting GET /meetings with API key: {api_key[:5]}...")
headers = {
    "x-api-key": api_key,
    "Content-Type": "application/json"
}

response = requests.get(f"{gateway_url}/meetings", headers=headers)
print(f"Status: {response.status_code}")
print(f"Response: {response.text[:200]}...")

# Test create bot
print("\nTesting POST /bots...")
payload = {
    "platform": "google_meet",
    "meeting_url": "https://meet.google.com/hxe-ihzd-csh",
    "bot_name": "TestScript"
}

response = requests.post(f"{gateway_url}/bots", headers=headers, json=payload)
print(f"Status: {response.status_code}")
print(f"Response: {response.text[:200]}...")

if response.status_code == 201:
    meeting_id = response.json()["id"]
    print(f"\nCreated meeting with ID: {meeting_id}")
    
    # Test get transcript
    print(f"\nTesting GET /meeting/transcript for meeting...")
    params = {
        "platform": "google_meet",
        "meeting_url": "https://meet.google.com/hxe-ihzd-csh"
    }
    response = requests.get(f"{gateway_url}/meeting/transcript", headers=headers, params=params)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:200]}...")
    
    # Test stop bot
    print(f"\nTesting DELETE /bots/{meeting_id}...")
    response = requests.delete(f"{gateway_url}/bots/{meeting_id}", headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:200]}...")
else:
    print("Bot creation failed, skipping further tests") 