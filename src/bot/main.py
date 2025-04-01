import os
import time
import random
import logging
import requests
import json
from dotenv import load_dotenv
import threading
import websocket
import sys
from typing import Dict, Any

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("bot")

# Get environment variables
USER_ID = os.getenv("USER_ID")
MEETING_ID = os.getenv("MEETING_ID")
TRANSCRIPTION_SERVICE = os.getenv("TRANSCRIPTION_SERVICE", "http://transcription-service:8080")

if not USER_ID or not MEETING_ID:
    logger.error("USER_ID and MEETING_ID must be provided as environment variables")
    sys.exit(1)

logger.info(f"Starting bot for user {USER_ID}, meeting {MEETING_ID}")

class Bot:
    def __init__(self, user_id: str, meeting_id: str, transcription_service: str):
        self.user_id = user_id
        self.meeting_id = meeting_id
        self.transcription_service = transcription_service
        self.running = True
        self.ws = None
        self.heartbeat_thread = None
        
    def start(self):
        """Start the bot processing"""
        logger.info("Bot starting...")
        
        # In a real scenario, we'd connect to a meeting/audio source here
        # For this example, we'll simulate sending periodic transcription data
        
        # Start a heartbeat thread
        self.heartbeat_thread = threading.Thread(target=self.heartbeat_loop)
        self.heartbeat_thread.daemon = True
        self.heartbeat_thread.start()
        
        try:
            # Main processing loop - in a real scenario, this would process audio
            # and send it to transcription service
            while self.running:
                # Simulate processing time
                time.sleep(5)
                
                # Simulate sending audio to transcription service and getting back transcription
                # In a real application, this would be actual audio processing
                self.simulate_transcription()
                
        except KeyboardInterrupt:
            logger.info("Bot shutting down gracefully...")
        except Exception as e:
            logger.error(f"Error in bot: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the bot processing"""
        logger.info("Stopping bot...")
        self.running = False
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=2)
    
    def heartbeat_loop(self):
        """Send periodic heartbeats to indicate the bot is alive"""
        while self.running:
            try:
                # In a real implementation, you might update a ConfigMap 
                # or another service to indicate the bot is still running
                logger.debug("Heartbeat...")
                time.sleep(10)
            except Exception as e:
                logger.error(f"Error in heartbeat: {e}")
    
    def simulate_transcription(self):
        """Simulate getting a transcription and sending it to the service"""
        try:
            # List of sample transcriptions to simulate a conversation
            samples = [
                "Hello, can everyone hear me?",
                "I think we should discuss the quarterly results first.",
                "The numbers are looking good for Q2.",
                "Let's move on to the next agenda item.",
                "Does anyone have questions about the new project?",
                "I'll follow up on that action item.",
                "Thanks everyone for joining today's meeting."
            ]
            
            # Pick a random sample
            content = random.choice(samples)
            
            # Simulate different speakers
            speaker = f"Speaker-{random.randint(1, 3)}"
            
            # Simulate a confidence score
            confidence = random.randint(70, 99)
            
            # Log the transcription
            logger.info(f"Transcription: [{speaker}] {content} (confidence: {confidence}%)")
            
            # Send to transcription service
            self.send_transcription(content, speaker, confidence)
            
        except Exception as e:
            logger.error(f"Error simulating transcription: {e}")
    
    def send_transcription(self, content: str, speaker: str = None, confidence: int = None):
        """Send a transcription to the transcription service"""
        try:
            # Prepare the data
            data = {
                "meeting_id": self.meeting_id,
                "content": content,
                "speaker": speaker,
                "confidence": confidence
            }
            
            # Send to the transcription service
            response = requests.post(
                f"{self.transcription_service}/transcription",
                json=data,
                timeout=5
            )
            
            if response.status_code != 200:
                logger.error(f"Error sending transcription: {response.status_code} - {response.text}")
            else:
                logger.debug("Transcription sent successfully")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error sending transcription: {e}")
        except Exception as e:
            logger.error(f"Error sending transcription: {e}")

if __name__ == "__main__":
    # Create and start the bot
    bot = Bot(USER_ID, MEETING_ID, TRANSCRIPTION_SERVICE)
    
    try:
        bot.start()
    except KeyboardInterrupt:
        bot.stop()
    except Exception as e:
        logger.error(f"Unhandled error: {e}")
        bot.stop() 