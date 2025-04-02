import docker
import logging
import os
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class DockerClient:
    """Client for Docker operations in local development environment"""
    
    def __init__(self):
        """Initialize Docker client"""
        self.client = docker.from_env()
        
        # Bot container configuration
        self.bot_image = os.getenv("BOT_IMAGE", "bot:latest")
        self.transcription_service = os.getenv("TRANSCRIPTION_SERVICE", "http://transcription-service:8080")
        self.network_name = os.getenv("DOCKER_NETWORK", "vexa_default")
    
    def create_bot_container(self, user_id: str, meeting_id: str, meeting_url: Optional[str] = None) -> Dict[str, Any]:
        """Create a new bot container for specific user and meeting"""
        container_name = f"bot-{user_id}-{meeting_id}"
        
        # Check if container already exists
        try:
            existing_container = self.client.containers.get(container_name)
            if existing_container:
                logger.info(f"Container {container_name} already exists with status: {existing_container.status}")
                
                # Start container if it's not running
                if existing_container.status != "running":
                    existing_container.start()
                    logger.info(f"Started existing container {container_name}")
                
                return {"status": "exists", "container_name": container_name}
        except docker.errors.NotFound:
            # Container doesn't exist, continue to create it
            pass
        except Exception as e:
            logger.error(f"Error checking container existence: {e}")
            raise
        
        # Set default meeting URL if not provided
        if not meeting_url:
            meeting_url = "https://meet.google.com/xxx-xxxx-xxx"
            
        logger.info(f"Creating bot container for meeting URL: {meeting_url}")
        
        # Create container
        try:
            container = self.client.containers.run(
                image=self.bot_image,
                name=container_name,
                detach=True,
                network=self.network_name,
                environment={
                    "USER_ID": user_id,
                    "MEETING_ID": meeting_id,
                    "MEETING_URL": meeting_url,
                    "TRANSCRIPTION_SERVICE": self.transcription_service
                },
                restart_policy={"Name": "on-failure", "MaximumRetryCount": 3}
            )
            
            logger.info(f"Created container {container_name}")
            return {"status": "created", "container_name": container_name}
        except Exception as e:
            logger.error(f"Error creating container: {e}")
            raise
    
    def delete_bot_container(self, user_id: str, meeting_id: Optional[str] = None) -> Dict[str, Any]:
        """Delete a bot container by user_id and optionally meeting_id"""
        try:
            if meeting_id:
                container_name = f"bot-{user_id}-{meeting_id}"
                container = self.client.containers.get(container_name)
                container.stop()
                container.remove()
                logger.info(f"Deleted container {container_name}")
                return {"status": "deleted", "container_name": container_name}
            else:
                # Delete all containers for user
                containers = self.client.containers.list(
                    all=True, 
                    filters={"name": f"bot-{user_id}"}
                )
                for container in containers:
                    container.stop()
                    container.remove()
                    logger.info(f"Deleted container {container.name}")
                return {"status": "deleted", "count": len(containers)}
        except docker.errors.NotFound:
            logger.warning(f"Container not found for user {user_id}")
            return {"status": "not_found"}
        except Exception as e:
            logger.error(f"Error deleting container: {e}")
            raise
    
    def get_bot_status(self, user_id: str) -> list:
        """Get status of all bot containers for a user"""
        try:
            containers = self.client.containers.list(
                all=True, 
                filters={"name": f"bot-{user_id}"}
            )
            
            result = []
            for container in containers:
                # Extract meeting_id from container name (format: bot-{user_id}-{meeting_id})
                name_parts = container.name.split('-')
                meeting_id = name_parts[2] if len(name_parts) > 2 else "unknown"
                
                result.append({
                    "container_name": container.name,
                    "user_id": user_id,
                    "meeting_id": meeting_id,
                    "status": container.status,
                    "creation_time": container.attrs['Created'] if 'Created' in container.attrs else None
                })
            
            return result
        except Exception as e:
            logger.error(f"Error getting container status: {e}")
            raise 