import requests
import requests_unixsocket # Use this directly
import logging
import json
import uuid
import os
from config import BOT_IMAGE_NAME, DOCKER_NETWORK

logger = logging.getLogger(__name__)

# Global session for requests_unixsocket
_socket_session = None

def get_socket_session():
    """Initializes and returns a requests_unixsocket session."""
    global _socket_session
    if _socket_session is None:
        try:
            logger.info("Initializing requests_unixsocket session...")
            _socket_session = requests_unixsocket.Session()
            # Simple test: Get Docker version via socket
            response = _socket_session.get('http+unix://%2Fvar%2Frun%2Fdocker.sock/version')
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            logger.info(f"requests_unixsocket session initialized. Docker API version: {response.json().get('ApiVersion')}")
        except Exception as e:
            logger.error(f"Failed to initialize requests_unixsocket session: {e}", exc_info=True)
            _socket_session = None
            raise
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

def start_bot_container(platform: str, meeting_url: str, bot_name: str, token: str) -> str | None:
    """Starts a vexa-bot container using requests_unixsocket."""
    session = get_socket_session()
    if not session:
        logger.error("Cannot start bot container, requests_unixsocket session not available.")
        return None
        
    connection_id = str(uuid.uuid4())
    container_name = f"vexa-bot-{platform}-{connection_id[:8]}"

    # Construct the BOT_CONFIG environment variable
    bot_config = {
        "platform": platform,
        "meetingUrl": meeting_url,
        "botName": bot_name,
        "token": token,
        "connectionId": connection_id,
        "automaticLeave": {
            "waitingRoomTimeout": 300000,
            "noOneJoinedTimeout": 300000,
            "everyoneLeftTimeout": 300000
        }
    }
    bot_config_json = json.dumps(bot_config)
    
    environment = [
        f"BOT_CONFIG={bot_config_json}",
        "PLATFORM=" + platform,
        "TOKEN=" + token,
        "MEETING_URL=" + meeting_url,
        "TRANSCRIPTION_SERVICE=ws://whisperlive:9090"
    ]

    # Docker API payload for creating a container
    create_payload = {
        "Image": BOT_IMAGE_NAME,
        "Env": environment,
        "HostConfig": {
            "NetworkMode": DOCKER_NETWORK,
            "AutoRemove": False
        },
    }

    create_url = f'http+unix://%2Fvar%2Frun%2Fdocker.sock/containers/create?name={container_name}'
    start_url_template = 'http+unix://%2Fvar%2Frun%2Fdocker.sock/containers/{}/start'

    try:
        logger.info(f"Attempting to create bot container '{container_name}' ({BOT_IMAGE_NAME}) via socket...")
        # Create the container
        response = session.post(create_url, json=create_payload)
        response.raise_for_status() # Check for API errors
        container_info = response.json()
        container_id = container_info.get('Id')
        
        if not container_id:
            logger.error(f"Failed to create container: No ID in response: {container_info}")
            return None
            
        logger.info(f"Container {container_id} created. Starting...")
        
        # Start the container
        start_url = start_url_template.format(container_id)
        response = session.post(start_url)

        # Check status code for start success (204 No Content is typical)
        if response.status_code != 204:
             logger.error(f"Failed to start container {container_id}. Status: {response.status_code}, Response: {response.text}")
             # Attempt to remove the created container if start failed?
             # We might not want to remove if AutoRemove is False, to allow debugging
             # try:
             #     remove_url = f'http+unix://%2Fvar%2Frun%2Fdocker.sock/containers/{container_id}?force=true'
             #     session.delete(remove_url)
             # except Exception as rm_err:
             #     logger.warning(f"Failed to remove container {container_id} after start failure: {rm_err}")
             return None
             
        logger.info(f"Successfully started container {container_id} for meeting: {meeting_url}")
        return container_id
        
    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP error communicating with Docker socket: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error starting container via socket: {e}", exc_info=True)
    
    return None

# TODO: Implement stop/status functions using requests_unixsocket
def stop_bot_container(container_id: str) -> bool:
    """Stops a container using its ID via requests_unixsocket.

    Args:
        container_id: The ID of the container to stop.

    Returns:
        True if the stop command was sent successfully (or container not found),
        False otherwise.
    """
    session = get_socket_session()
    if not session:
        logger.error(f"Cannot stop container {container_id}, requests_unixsocket session not available.")
        return False

    stop_url = f'http+unix://%2Fvar%2Frun%2Fdocker.sock/containers/{container_id}/stop'
    # Optional: URL to remove the container afterwards if AutoRemove=False was used during creation
    # remove_url = f'http+unix://%2Fvar%2Frun%2Fdocker.sock/containers/{container_id}?force=true' 

    try:
        logger.info(f"Attempting to stop container {container_id} via socket...")
        # Send POST request to stop the container. Docker waits for it to stop.
        # Timeout can be added via query param `t` (e.g., ?t=5 for 5 seconds)
        response = session.post(stop_url)
        
        # Check status code: 204 No Content (success), 304 Not Modified (already stopped), 404 Not Found
        if response.status_code == 204:
            logger.info(f"Successfully sent stop command to container {container_id}.")
            # Optional: Remove the container if needed
            # response_remove = session.delete(remove_url)
            # response_remove.raise_for_status()
            # logger.info(f"Successfully removed container {container_id}.")
            return True
        elif response.status_code == 304:
            logger.warning(f"Container {container_id} was already stopped.")
            return True
        elif response.status_code == 404:
            logger.warning(f"Container {container_id} not found, assuming already stopped/removed.")
            return True 
        else:
            # Raise exception for other errors (like 500)
            response.raise_for_status()
            return True # Should not be reached if raise_for_status() works

    except requests.exceptions.RequestException as e:
        # Handle 404 specifically if raise_for_status() doesn't catch it as expected
        if e.response is not None and e.response.status_code == 404:
            logger.warning(f"Container {container_id} not found (exception check), assuming already stopped/removed.")
            return True
        logger.error(f"HTTP error stopping container {container_id}: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Unexpected error stopping container {container_id}: {e}", exc_info=True)
        return False 