# EduVoice AI Assistant

A full-stack voice-enabled assistant for students, parents, and admins. Includes authentication, chat with session history, rewards view for parents, and document ingestion/search for admins.

## Tech Stack
- Frontend: React (React Router), CSS
- Backend: FastAPI (Python)
- Auth: Google Sign-In + JWT
- Storage: Local uploads; vector search via backend

## Quick Start

### Backend
1. Create and activate a Python venv (Windows):
```bash
cd backend
..\pbnv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend
1. Install and run:
```bash
cd frontend
npm install
npm start
```
2. App runs at `http://localhost:3000` and expects the backend at `http://127.0.0.1:8000`.

## Features
- Google Sign-In → backend issues JWT for all API calls
- Role-based redirects: admin, parent, student
- Parent dashboard: reward points and chat
- Admin dashboard: upload/search/delete documents, user overview
- Chatbot: text/mic input, type indicator, stop generation, session history

## Environment
- Update Google Client ID in `frontend/src/Login.jsx` if needed
- Backend base URL: `http://127.0.0.1:8000`

## Scripts
- Backend: `uvicorn main:app --reload`
- Frontend: `npm start`

## Notes
- Ensure PDFs to ingest are placed via the Admin dashboard upload
- Auth token is stored in `localStorage` as `access_token`

## License
MIT
