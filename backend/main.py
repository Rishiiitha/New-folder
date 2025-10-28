import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables (like your .env file)
load_dotenv()

# --- 1. Import Your Routers ---
# Import the 'router' variable from each of your files
from auth_routes import router as auth_router
from apibot import router as bot_router
from ingest import router as ingest_router

# Create the main FastAPI application
app = FastAPI()

# --- 2. Add CORS Middleware ---
# This is required to allow your React frontend (running on http://localhost:3000)
# to communicate with this backend (running on http://localhost:8000).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins (for development)
    # For production, you should restrict this to your frontend's domain:
    # allow_origins=["http://localhost:3000", "http://your-production-site.com"]
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods
    allow_headers=["*"],  # Allows all headers
)

# --- 3. Include All Your Routers ---
# We add a "prefix" to keep your API organized.
#
# /auth/gsi_login
app.include_router(auth_router, prefix="/auth")
#
# /bot/ask
app.include_router(bot_router, prefix="/bot")
#
# /ingest/upload, /ingest/list, etc.
app.include_router(ingest_router, prefix="/ingest")


# --- 4. Root Endpoint ---
@app.get("/")
def read_root():
    return {"message": "Welcome to your combined backend API"}


# --- 5. Run the App ---
if __name__ == "__main__":
    # This allows you to run the app by typing 'python main.py'
    # although 'uvicorn main:app --reload' is usually better.
    uvicorn.run(app, host="0.0.0.0", port=8000)