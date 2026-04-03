import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
load_dotenv()
from auth_routes import router as auth_router
from apibot import router as bot_router
from ingest import router as ingest_router
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth")

app.include_router(bot_router, prefix="/bot")

app.include_router(ingest_router, prefix="/ingest")

@app.get("/")
def read_root():
    return {"message": "Welcome to your combined backend API"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)