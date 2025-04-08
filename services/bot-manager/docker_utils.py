import requests_unixsocket
import logging
import json
import uuid
import os
import time
from typing import Optional

# Import the Platform class from shared models
from shared_models.schemas import Platform

# Assuming these are still needed from config or env
DOCKER_HOST = os.environ.get("DOCKER_HOST", "unix://var/run/docker.sock")
DOCKER_NETWORK = os.environ.get("DOCKER_NETWORK", "vexa_default")
BOT_IMAGE_NAME = os.environ.get("BOT_IMAGE", "vexa-bot:latest")

logger = logging.getLogger("bot_manager.docker_utils")

# Global session for requests_unixsocket
_socket_session = None

# Define a local exception
class DockerConnectionError(Exception):
    pass

def get_socket_session(max_retries=3, delay=2):
    """Initializes and returns a requests_unixsocket session with retries."""
    global _socket_session
    if _socket_session is None:
        logger.info(f"Attempting to initialize requests_unixsocket session for {DOCKER_HOST}...")
        retries = 0
        # Extract socket path correctly AND ensure it's absolute
        socket_path_relative = DOCKER_HOST.split('//', 1)[1]
        socket_path_abs = f"/{socket_path_relative}" # Prepend slash for absolute path

        # URL encode path separately using the absolute path
        # The http+unix scheme requires the encoded absolute path
        socket_path_encoded = socket_path_abs.replace("/", "%2F")
        socket_url = f'http+unix://{socket_path_encoded}'

        while retries < max_retries:
            try:
                # Check socket file exists before attempting connection using the absolute path
                logger.debug(f"Checking for socket file at absolute path: {socket_path_abs}") # Added debug log
                if not os.path.exists(socket_path_abs):
                     # Ensure the error message shows the absolute path being checked
                     raise FileNotFoundError(f"Docker socket file not found at: {socket_path_abs}")

                logger.debug(f"Attempt {retries+1}/{max_retries}: Creating session.")
                temp_session = requests_unixsocket.Session()

                # Test connection by getting Docker version via the correctly formed URL
                logger.debug(f"Attempt {retries+1}/{max_retries}: Getting Docker version via {socket_url}/version")
                response = temp_session.get(f'{socket_url}/version')
                response.raise_for_status() # Raise HTTPError for bad responses
                version_data = response.json()
                api_version = version_data.get('ApiVersion')
                logger.info(f"requests_unixsocket session initialized. Docker API version: {api_version}")
                _socket_session = temp_session # Assign only on success
                return _socket_session

            except FileNotFoundError as e:
                 # Log the actual exception message which now includes the absolute path
                 logger.warning(f"Attempt {retries+1}/{max_retries}: {e}. Retrying in {delay}s...")
            except requests_unixsocket.exceptions.ConnectionError as e:
                 logger.warning(f"Attempt {retries+1}/{max_retries}: Socket connection error ({e}). Is Docker running? Retrying in {delay}s...")
            except requests_unixsocket.exceptions.HTTPError as e:
                logger.error(f"Attempt {retries+1}/{max_retries}: HTTP error communicating with Docker socket: {e}", exc_info=True)
                 # Don't retry on HTTP errors like 4xx/5xx immediately, might be persistent issue
                break
            except Exception as e:
                logger.error(f"Attempt {retries+1}/{max_retries}: Failed to initialize requests_unixsocket session: {e}", exc_info=True)

            retries += 1
            if retries < max_retries:
                time.sleep(delay)
            else:
                logger.error(f"Failed to connect to Docker socket at {DOCKER_HOST} after {max_retries} attempts.")
                _socket_session = None
                raise DockerConnectionError(f"Could not connect to Docker socket after {max_retries} attempts.")

    return _socket_session

def close_docker_client(): # Keep name for compatibility in main.py
    """Closes the requests_unixsocket session."""
    global _socket_session
    if _socket_session:
        logger.info("Closing requests_unixsocket session.")
        try:
            _socket_session.close()
        except Exception as e:
            logger.warning(f"Error closing requests_unixsocket session: {e}")
        _socket_session = None

def start_bot_container(
    meeting_id: int,
    meeting_url: Optional[str],
    platform: str, # External name (e.g., google_meet)
    bot_name: Optional[str],
    user_token: str, # *** ADDED ***
    native_meeting_id: str # *** ADDED ***
) -> Optional[str]:
    """Starts a vexa-bot container using requests_unixsocket.
    
    Args:
        meeting_id: The internal database ID for the meeting.
        meeting_url: The *constructed* meeting URL (can be None).
        platform: The platform string (e.g., 'google_meet').
        bot_name: Optional name for the bot.
        user_token: The API token of the user requesting the bot. # *** ADDED doc ***
        native_meeting_id: The platform-specific meeting ID (e.g., 'xyz-abc-pdq'). # *** ADDED doc ***
        
    Returns:
        The container ID if successful, None otherwise.
    """
    session = get_socket_session()
    if not session:
        logger.error("Cannot start bot container, requests_unixsocket session not available.")
        return None

    container_name = f"vexa-bot-{meeting_id}-{uuid.uuid4().hex[:8]}"
    if not bot_name:
        bot_name = f"VexaBot-{uuid.uuid4().hex[:6]}"

    # Construct BOT_CONFIG JSON - Use external platform name directly
    bot_config_data = {
        "meeting_id": meeting_id,         # Keep internal ID 
        "platform": platform,             # Use original external platform name
        "meetingUrl": meeting_url,
        "botName": bot_name,
        "token": user_token,              # Use the passed user_token
        "nativeMeetingId": native_meeting_id, # Use the passed native_meeting_id
        "connectionId": "",               # Keep default empty string for now
        "automaticLeave": {
            "waitingRoomTimeout": 300000,
            "noOneJoinedTimeout": 300000,
            "everyoneLeftTimeout": 300000
        }
    }
    bot_config_json = json.dumps(bot_config_data)

    logger.info(f"Bot config: {bot_config_json}") # Log the full config

    environment = [
        f"BOT_CONFIG={bot_config_json}",
        f"WHISPER_LIVE_URL={os.getenv('WHISPER_LIVE_URL', 'ws://whisperlive:9090')}",
        f"LOG_LEVEL={os.getenv('LOG_LEVEL', 'INFO').upper()}",
    ]

    # Ensure absolute path for URL encoding here as well
    socket_path_relative = DOCKER_HOST.split('//', 1)[1]
    socket_path_abs = f"/{socket_path_relative}"
    socket_path_encoded = socket_path_abs.replace("/", "%2F")
    socket_url_base = f'http+unix://{socket_path_encoded}'

    # Docker API payload for creating a container
    create_payload = {
        "Image": BOT_IMAGE_NAME,
        "Env": environment,
        "HostConfig": {
            "NetworkMode": DOCKER_NETWORK,
            "AutoRemove": True
        },
    }

    create_url = f'{socket_url_base}/containers/create?name={container_name}'
    start_url_template = f'{socket_url_base}/containers/{{}}/start'

    try:
        logger.info(f"Attempting to create bot container '{container_name}' ({BOT_IMAGE_NAME}) via socket ({socket_url_base})...")
        response = session.post(create_url, json=create_payload)
        response.raise_for_status()
        container_info = response.json()
        container_id = container_info.get('Id')

        if not container_id:
            logger.error(f"Failed to create container: No ID in response: {container_info}")
            return None

        logger.info(f"Container {container_id} created. Starting...")

        start_url = start_url_template.format(container_id)
        response = session.post(start_url)

        if response.status_code != 204:
            logger.error(f"Failed to start container {container_id}. Status: {response.status_code}, Response: {response.text}")
            return None

        logger.info(f"Successfully started container {container_id} for meeting: {meeting_id}")
        return container_id

    except requests_unixsocket.exceptions.RequestException as e:
        logger.error(f"HTTP error communicating with Docker socket: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error starting container via socket: {e}", exc_info=True)

    return None

def stop_bot_container(container_id: str) -> bool:
    """Stops a container using its ID via requests_unixsocket."""
    session = get_socket_session()
    if not session:
        logger.error(f"Cannot stop container {container_id}, requests_unixsocket session not available.")
        return False

    # Ensure absolute path for URL encoding here as well
    socket_path_relative = DOCKER_HOST.split('//', 1)[1]
    socket_path_abs = f"/{socket_path_relative}"
    socket_path_encoded = socket_path_abs.replace("/", "%2F")
    socket_url_base = f'http+unix://{socket_path_encoded}'
    
    stop_url = f'{socket_url_base}/containers/{container_id}/stop'
    # Since AutoRemove=True, we don't need a separate remove call

    try:
        logger.info(f"Attempting to stop container {container_id} via socket ({stop_url})...") # Log stop URL
        # Send POST request to stop the container. Docker waits for it to stop.
        # Timeout can be added via query param `t` (e.g., ?t=10 for 10 seconds)
        response = session.post(f"{stop_url}?t=10") 
        
        # Check status code: 204 No Content (success), 304 Not Modified (already stopped), 404 Not Found
        if response.status_code == 204:
            logger.info(f"Successfully sent stop command to container {container_id}.")
            return True
        elif response.status_code == 304:
            logger.warning(f"Container {container_id} was already stopped.")
            return True
        elif response.status_code == 404:
            logger.warning(f"Container {container_id} not found, assuming already stopped/removed.")
            return True 
        else:
            # Raise exception for other errors (like 500)
            logger.error(f"Error stopping container {container_id}. Status: {response.status_code}, Body: {response.text}")
            response.raise_for_status()
            return False # Should not be reached if raise_for_status() works

    except requests_unixsocket.exceptions.RequestException as e:
        # Handle 404 specifically if raise_for_status() doesn't catch it as expected
        if hasattr(e, 'response') and e.response is not None and e.response.status_code == 404:
            logger.warning(f"Container {container_id} not found (exception check), assuming already stopped/removed.")
            return True
        logger.error(f"HTTP error stopping container {container_id}: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Unexpected error stopping container {container_id}: {e}", exc_info=True)
        return False 