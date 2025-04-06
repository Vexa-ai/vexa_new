import uvicorn
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
import os
from dotenv import load_dotenv
import json # For request body processing

load_dotenv()

# Configuration from environment variables - UPDATE URLs
ADMIN_API_URL = os.getenv("ADMIN_API_URL", "http://admin-api:8001") # New service
BOT_MANAGER_URL = os.getenv("BOT_MANAGER_URL", "http://bot-manager:8080") # Corrected default name
TRANSCRIPTION_COLLECTOR_URL = os.getenv("TRANSCRIPTION_COLLECTOR_URL", "http://transcription-collector:8000") # Use collector service name

app = FastAPI(title="Vexa API Gateway", description="Main entry point for Vexa APIs")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- HTTP Client --- 
# Use a single client instance for connection pooling
@app.on_event("startup")
async def startup_event():
    app.state.http_client = httpx.AsyncClient()

@app.on_event("shutdown")
async def shutdown_event():
    await app.state.http_client.aclose()

# --- Helper for Forwarding --- 
async def forward_request(client: httpx.AsyncClient, method: str, url: str, request: Request) -> Response:
    # Copy original headers, converting to a standard dict
    # Exclude host, content-length, transfer-encoding as they are handled by httpx/server
    excluded_headers = {"host", "content-length", "transfer-encoding"}
    headers = {k.lower(): v for k, v in request.headers.items() if k.lower() not in excluded_headers}
    
    # Determine target service based on URL path prefix
    is_admin_request = url.startswith(f"{ADMIN_API_URL}/admin")
    
    # Forward appropriate auth header if present
    if is_admin_request:
        admin_key = request.headers.get("x-admin-api-key")
        if admin_key:
            headers["x-admin-api-key"] = admin_key
        # else: Handle missing admin key? Or let admin-api handle it? Let admin-api handle.
    else:
        # Forward client API key for bot-manager and transcription-collector
        client_key = request.headers.get("x-api-key")
        if client_key:
            headers["x-api-key"] = client_key 
        # else: Let downstream service handle missing key
    
    content = await request.body()
    
    try:
        resp = await client.request(method, url, headers=headers, content=content)
        # Return downstream response directly (including headers, status code)
        return Response(content=resp.content, status_code=resp.status_code, headers=dict(resp.headers))
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Service unavailable: {exc}")

# --- Root Endpoint --- 
@app.get("/")
async def root():
    return {"message": "Welcome to the Vexa API Gateway"}

# --- Bot Manager Routes --- 
@app.post("/bots")
async def request_bot_proxy(request: Request):
    url = f"{BOT_MANAGER_URL}/bots"
    return await forward_request(app.state.http_client, "POST", url, request)

@app.delete("/bots/{platform}/{platform_specific_id}/{token}")
async def stop_bot_proxy(platform: str, platform_specific_id: str, token: str, request: Request):
    url = f"{BOT_MANAGER_URL}/bots/{platform}/{platform_specific_id}/{token}"
    return await forward_request(app.state.http_client, "DELETE", url, request)

# --- Transcription Collector Routes --- 
@app.get("/meetings")
async def get_meetings_proxy(request: Request):
    url = f"{TRANSCRIPTION_COLLECTOR_URL}/meetings"
    # Auth header (X-API-Key) is handled by forward_request
    return await forward_request(app.state.http_client, "GET", url, request)

@app.get("/meeting/transcript")
async def get_meeting_transcript_proxy(request: Request):
    # Pass query parameters through
    url = f"{TRANSCRIPTION_COLLECTOR_URL}/meeting/transcript?{request.query_params}"
    # Auth header (X-API-Key) is handled by forward_request
    return await forward_request(app.state.http_client, "GET", url, request)

# --- Admin API Routes (Placeholder) ---
# Auth header (X-Admin-API-Key) is handled by forward_request
@app.post("/admin/users")
async def create_user_proxy(request: Request):
    url = f"{ADMIN_API_URL}/admin/users"
    return await forward_request(app.state.http_client, "POST", url, request)

@app.get("/admin/users")
async def list_users_proxy(request: Request):
    url = f"{ADMIN_API_URL}/admin/users?{request.query_params}"
    return await forward_request(app.state.http_client, "GET", url, request)

@app.post("/admin/users/{user_id}/tokens")
async def create_token_proxy(user_id: int, request: Request):
    url = f"{ADMIN_API_URL}/admin/users/{user_id}/tokens"
    return await forward_request(app.state.http_client, "POST", url, request)

# --- Old Routes (Commented out) --- 
# @app.post("/bot/run")
# async def run_bot(request: Request):
#     data = await request.json()
#     if "meeting_url" not in data:
#         data["meeting_url"] = "https://meet.google.com/xxx-xxxx-xxx"
#     async with httpx.AsyncClient() as client:
#         response = await client.post(f"{BOT_MANAGER_URL}/bot/run", json=data)
#         return JSONResponse(content=response.json(), status_code=response.status_code)
# @app.post("/bot/stop")
# async def stop_bot(request: Request):
#     data = await request.json()
#     async with httpx.AsyncClient() as client:
#         response = await client.post(f"{BOT_MANAGER_URL}/bot/stop", json=data)
#         return JSONResponse(content=response.json(), status_code=response.status_code)
# @app.get("/bot/status/{user_id}")
# async def bot_status(user_id: str):
#     async with httpx.AsyncClient() as client:
#         response = await client.get(f"{BOT_MANAGER_URL}/bot/status/{user_id}")
#         return JSONResponse(content=response.json(), status_code=response.status_code)
# @app.get("/transcript/{user_id}/{meeting_id}")
# async def get_transcript(user_id: str, meeting_id: str):
#     async with httpx.AsyncClient() as client:
#         response = await client.get(f"{TRANSCRIPTION_COLLECTOR_URL}/transcript/{user_id}/{meeting_id}") # Corrected URL
#         return JSONResponse(content=response.json(), status_code=response.status_code)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 