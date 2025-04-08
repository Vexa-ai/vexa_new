# vexa_client.py

import requests
from typing import Optional, List, Dict, Any
import os
from urllib.parse import urljoin
import time # Import time for sleep
import re # Import re for parsing meeting ID

# Default Base URL (can be overridden)
DEFAULT_BASE_URL = "http://localhost:8056" 

class VexaClientError(Exception):
    """Custom exception for Vexa client errors."""
    pass

class VexaClient:
    """
    A Python client for interacting with the Vexa API Gateway.
    """

    def __init__(self, 
                 base_url: str = DEFAULT_BASE_URL, 
                 api_key: Optional[str] = None, 
                 admin_key: Optional[str] = None):
        """
        Initializes the Vexa API client.

        Args:
            base_url: The base URL of the Vexa API Gateway.
            api_key: The API key for regular user operations (X-API-Key).
            admin_key: The API key for administrative operations (X-Admin-API-Key).
        """
        # Ensure base_url is a string
        if not isinstance(base_url, str):
            base_url = str(base_url)
        
        self.base_url = base_url
        self._api_key = api_key
        self._admin_key = admin_key
        self._session = requests.Session()

    def _get_headers(self, api_type: str = 'user') -> Dict[str, str]:
        """Prepares headers for the request based on API type."""
        headers = {"Content-Type": "application/json"}
        if api_type == 'admin':
            if not self._admin_key:
                raise VexaClientError("Admin API key is required for this operation but was not provided.")
            headers["X-Admin-API-Key"] = self._admin_key
        elif api_type == 'user':
            if not self._api_key:
                raise VexaClientError("User API key is required for this operation but was not provided.")
            headers["X-API-Key"] = self._api_key
        else:
             raise ValueError("Invalid api_type specified. Use 'user' or 'admin'.")
        return headers

    def _request(self, 
                 method: str, 
                 path: str, 
                 api_type: str = 'user', 
                 params: Optional[Dict[str, Any]] = None, 
                 json_data: Optional[Dict[str, Any]] = None) -> Any:
        """
        Internal helper method to make requests to the API gateway.

        Args:
            method: HTTP method (e.g., 'GET', 'POST', 'DELETE').
            path: API endpoint path (e.g., '/bots').
            api_type: Type of API key required ('user' or 'admin').
            params: Optional dictionary of query parameters.
            json_data: Optional dictionary for the JSON request body.

        Returns:
            The JSON response from the API.

        Raises:
            VexaClientError: If the required API key is missing.
            requests.exceptions.RequestException: For connection or other request errors.
            requests.exceptions.HTTPError: For non-2xx status codes.
        """
        url = urljoin(self.base_url, path)
        headers = self._get_headers(api_type)
        
        # Debug output - print URL and headers for troubleshooting
        print(f"\nDEBUG: Making {method} request to {url}")
        print(f"DEBUG: Headers: {headers}")
        print(f"DEBUG: Params: {params}")
        print(f"DEBUG: JSON data: {json_data}")
        
        try:
            response = self._session.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_data
            )
            # Debug response
            print(f"DEBUG: Response status: {response.status_code}")
            print(f"DEBUG: Response headers: {dict(response.headers)}")
            try:
                print(f"DEBUG: Response content: {response.text[:500]}...")
            except:
                print(f"DEBUG: Could not display response content")
                
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            
            # Handle cases where response might be empty (e.g., 204 No Content)
            if response.status_code == 204:
                return None 
            
            return response.json()
        except requests.exceptions.JSONDecodeError:
            raise VexaClientError(f"Failed to decode JSON response from {method} {url}. Status: {response.status_code}, Body: {response.text}")
        except requests.exceptions.HTTPError as e:
            # Attempt to include API error details if available
            try:
                error_details = e.response.json()
                detail_msg = error_details.get('detail', e.response.text)
            except requests.exceptions.JSONDecodeError:
                detail_msg = e.response.text
            raise VexaClientError(f"HTTP Error {e.response.status_code} for {method} {url}: {detail_msg}") from e
        except requests.exceptions.RequestException as e:
            raise VexaClientError(f"Request failed for {method} {url}: {e}") from e


    # --- Bot Management ---

    def request_bot(self, platform: str, native_meeting_id: str, bot_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Requests a new bot to join a meeting using platform and native ID.

        Args:
            platform: Platform identifier (e.g., 'google_meet', 'zoom').
            native_meeting_id: The platform-specific meeting identifier.
            bot_name: Optional name for the bot in the meeting.

        Returns:
            Dictionary representing the created/updated Meeting object.
        """
        payload = {"platform": platform, "native_meeting_id": native_meeting_id}
        if bot_name:
            payload["bot_name"] = bot_name
        return self._request("POST", "/bots", api_type='user', json_data=payload)

    def stop_bot(self, platform: str, native_meeting_id: str) -> Dict[str, Any]:
        """
        Stops a running bot for a specific meeting using platform and native ID.

        Args:
            platform: Platform identifier (e.g., 'google_meet', 'zoom').
            native_meeting_id: The platform-specific meeting identifier.

        Returns:
            Dictionary representing the updated Meeting object.
        """
        path = f"/bots/{platform}/{native_meeting_id}"
        return self._request("DELETE", path, api_type='user')

    # --- Transcriptions ---

    def get_meetings(self) -> List[Dict[str, Any]]:
        """
        Retrieves the list of meetings initiated by the user associated with the API key.

        Returns:
            List of dictionaries, each representing a Meeting object.
        """
        response = self._request("GET", "/meetings", api_type='user')
        # The API returns a dict {"meetings": [...]}, extract the list.
        return response.get("meetings", [])

    def get_transcript(self, platform: str, native_meeting_id: str) -> Dict[str, Any]:
        """
        Retrieves the transcript for a specific meeting using platform and native ID.

        Args:
            platform: Platform identifier (e.g., 'google_meet', 'zoom').
            native_meeting_id: The platform-specific meeting identifier.

        Returns:
            Dictionary containing meeting details and transcript segments.
        """
        path = f"/transcripts/{platform}/{native_meeting_id}"
        return self._request("GET", path, api_type='user')

    # --- Admin: User Management ---

    def create_user(self, email: str, name: Optional[str] = None, image_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Creates a new user (Admin Only).

        Args:
            email: The email address for the new user.
            name: Optional name for the user.
            image_url: Optional URL for the user's image.

        Returns:
            Dictionary representing the created User object.
        """
        payload = {"email": email}
        if name:
            payload["name"] = name
        if image_url:
            payload["image_url"] = image_url
        return self._request("POST", "/admin/users", api_type='admin', json_data=payload)

    def list_users(self, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Lists users in the system (Admin Only).

        Args:
            skip: Number of users to skip (for pagination).
            limit: Maximum number of users to return (for pagination).

        Returns:
            A list of dictionaries, each representing a User object.
        """
        params = {"skip": skip, "limit": limit}
        return self._request("GET", "/admin/users", api_type='admin', params=params)

    # --- Admin: Token Management ---

    def create_token(self, user_id: int) -> Dict[str, Any]:
        """
        Generates a new API token for a specific user (Admin Only).

        Args:
            user_id: The ID of the user for whom to create the token.

        Returns:
            Dictionary representing the created APIToken object.
        """
        return self._request("POST", f"/admin/users/{user_id}/tokens", api_type='admin')

# --- Example Usage and E2E Test ---
if __name__ == "__main__":
    # --- Configuration ---
    GATEWAY_URL = os.environ.get("VEXA_GATEWAY_URL", DEFAULT_BASE_URL)
    # Load Admin Key: Use env var or default assumed to be in compose/kube secrets
    # Defaulting to supersecretadmintoken if not set via env var
    ADMIN_API_KEY = os.environ.get("VEXA_ADMIN_API_KEY", "supersecretadmintoken") 
    TEST_USER_EMAIL = "test.e2e@example.com"
    
    print(f"--- Configuration ---")
    print(f"Gateway URL: {GATEWAY_URL}")
    print(f"Admin Key Used: {'*' * (len(ADMIN_API_KEY)-4)}{ADMIN_API_KEY[-4:]}" if ADMIN_API_KEY and len(ADMIN_API_KEY) > 4 else "Provided (short)")
    print(f"Test User Email: {TEST_USER_EMAIL}")

    admin_client = VexaClient(base_url=GATEWAY_URL, admin_key=ADMIN_API_KEY)
    user_api_key = None
    user_id = None

    # --- Setup: Ensure User and Token Exist --- 
    print("\n--- Setup: Ensuring Test User and API Key --- ")
    try:
        # 1. Find or create user
        print(f"Checking for user: {TEST_USER_EMAIL}...")
        # Note: Listing all users might be slow with many users. 
        # A dedicated GET /admin/users/by_email?email=... endpoint would be better.
        users = admin_client.list_users(limit=1000) # Assume test user is within first 1000
        found_user = next((u for u in users if u.get('email') == TEST_USER_EMAIL), None)
        
        if found_user:
            user_id = found_user['id']
            print(f"Found existing user ID: {user_id}")
        else:
            print(f"User not found. Creating user: {TEST_USER_EMAIL}...")
            new_user = admin_client.create_user(email=TEST_USER_EMAIL, name="E2E Test User")
            user_id = new_user['id']
            print(f"Created user ID: {user_id}")

        # 2. Create API token for the user
        # Note: This creates a new token every time the script runs.
        # Consider storing/reusing tokens if needed, but for testing, new one is fine.
        print(f"Creating token for user ID: {user_id}...")
        token_info = admin_client.create_token(user_id=user_id)
        user_api_key = token_info['token']
        print(f"Obtained User API Key: {'*' * (len(user_api_key)-4)}{user_api_key[-4:]}")

    except VexaClientError as e:
        print(f"*** Setup Failed: Could not ensure user/token using Admin API: {e} ***")
        print("   (Ensure the Admin API is running and the Admin Key is correct)")
        exit(1)
    except Exception as e:
         print(f"*** Setup Failed: An unexpected error occurred during setup: {e} ***")
         exit(1)
         
    if not user_api_key:
         print("*** Setup Failed: Could not obtain User API Key. ***")
         exit(1)

    # --- Initialize User Client with Obtained Key --- 
    user_client = VexaClient(base_url=GATEWAY_URL, api_key=user_api_key)

    # --- End-to-End Test --- 
    print(f"\n--- Running End-to-End Test against {GATEWAY_URL} ---")

    target_meeting_url = "https://meet.google.com/owp-ybqz-pgi"
    platform = "google_meet"
    
    # Extract native ID from URL
    match = re.search(r"meet.google.com/([a-z]{3}-[a-z]{4}-[a-z]{3})", target_meeting_url)
    if not match:
        print(f"Error: Could not extract valid Google Meet ID from URL: {target_meeting_url}")
        exit(1)
    native_meeting_id = match.group(1)
    print(f"Target Platform: {platform}")
    print(f"Target Native ID: {native_meeting_id}")

    bot_requested_successfully = False
    test_failed = False

    try:
        # 1. Request the bot
        print(f"\n1. Requesting bot for {platform} / {native_meeting_id}...")
        try:
            meeting_response = user_client.request_bot(platform=platform, native_meeting_id=native_meeting_id, bot_name="E2ETestBot")
            print(f"   Request Bot Response: {meeting_response}")
            if meeting_response.get('id') and meeting_response.get('status') in ['requested', 'active']:
                 print("   Bot requested successfully.")
                 bot_requested_successfully = True
            else:
                 print("   WARN: Bot request response did not indicate immediate success.")
                 # Continue anyway, maybe it starts slightly delayed
        except VexaClientError as e:
            print(f"   *** Error requesting bot: {e} ***")
            if "409" in str(e) or "already exists" in str(e).lower():
                print("   Conflict: Bot for this meeting might already be active. Attempting to proceed...")
                # Don't mark as success, but allow transcript check
            else:
                 test_failed = True # Mark test as failed if bot request fails for other reasons

        # Only proceed if the test hasn't definitively failed yet
        if not test_failed:
             # 2. Wait for transcription
            wait_time = 30
            print(f"\n2. Waiting {wait_time} seconds for bot to join and transcribe...")
            time.sleep(wait_time)

            # 3. Get transcript
            print(f"\n3. Attempting to get transcript for {platform} / {native_meeting_id}...")
            transcript_found = False
            try:
                transcript = user_client.get_transcript(platform=platform, native_meeting_id=native_meeting_id)
                print(f"   Transcript Response: {transcript}")
                segments = transcript.get('segments', [])
                if segments:
                    print(f"   SUCCESS: Found {len(segments)} transcript segments!")
                    for i, seg in enumerate(segments[:5]): # Print first 5 segments
                         print(f"     Segment {i+1}: [{seg.get('start_time')} - {seg.get('end_time')}] {seg.get('text')}")
                    transcript_found = True
                else:
                    print("   FAILURE: Transcript requested successfully, but no segments were found.")
                    test_failed = True
            except VexaClientError as e:
                print(f"   *** Error getting transcript: {e} ***")
                test_failed = True

            except Exception as e:
                print(f"\n*** An unexpected error occurred during the test: {e} ***")
                test_failed = True

    finally:
        # 4. Stop the bot (always attempt cleanup, even if test failed, but only if requested or conflicted)
        if bot_requested_successfully or (not test_failed and not bot_requested_successfully): # Attempt cleanup if bot was requested or conflicted
            print(f"\n4. Cleaning up: Stopping bot for {platform} / {native_meeting_id}...")
            try:
                stop_response = user_client.stop_bot(platform=platform, native_meeting_id=native_meeting_id)
                print(f"   Stop Bot Response: {stop_response}")
            except VexaClientError as e:
                print(f"   *** Error stopping bot during cleanup: {e} ***")
        else:
             print("\n4. Skipping cleanup: Bot was not successfully requested or test failed early.")

    # --- Test Result --- 
    print("\n--- End-to-End Test Result ---")
    if not test_failed and transcript_found:
        print("✅ SUCCESS: Bot joined and transcript segments were retrieved.")
        exit(0)
    else:
        print("❌ FAILURE: Test did not complete successfully.")
        exit(1) 