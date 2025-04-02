import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration from environment variables
BOT_MANAGER_URL = os.getenv("BOT_MANAGER_URL", "http://bot-manager-service:8080")
TRANSCRIPTION_URL = os.getenv("TRANSCRIPTION_URL", "http://transcription-service:8080")

app = FastAPI(title="Gateway API", description="API Gateway for Bot Management System")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Welcome to the Bot Management System Gateway API"}

@app.post("/bot/run")
async def run_bot(request: Request):
    """Forward bot run request to Bot Manager API"""
    data = await request.json()
    
    # Ensure meeting_url is present in the request
    if "meeting_url" not in data:
        data["meeting_url"] = "https://meet.google.com/xxx-xxxx-xxx"
    
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{BOT_MANAGER_URL}/bot/run", json=data)
        return JSONResponse(content=response.json(), status_code=response.status_code)

@app.post("/bot/stop")
async def stop_bot(request: Request):
    """Forward bot stop request to Bot Manager API"""
    data = await request.json()
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{BOT_MANAGER_URL}/bot/stop", json=data)
        return JSONResponse(content=response.json(), status_code=response.status_code)

@app.get("/bot/status/{user_id}")
async def bot_status(user_id: str):
    """Forward bot status request to Bot Manager API"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BOT_MANAGER_URL}/bot/status/{user_id}")
        return JSONResponse(content=response.json(), status_code=response.status_code)

@app.get("/transcript/{user_id}/{meeting_id}")
async def get_transcript(user_id: str, meeting_id: str):
    """Forward transcript retrieval request to Transcription Service"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{TRANSCRIPTION_URL}/transcript/{user_id}/{meeting_id}")
        return JSONResponse(content=response.json(), status_code=response.status_code)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 