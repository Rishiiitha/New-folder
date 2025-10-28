import os
from jose import jwt
import psycopg2
import json
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from dotenv import load_dotenv
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from starlette.responses import JSONResponse

# --- 1. CONFIGURATION ---
load_dotenv()
router = APIRouter()

# --- Google & JWT Secrets ---
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
JWT_SECRET = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"

# --- Database Config ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "Student_data")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "Veeraragava")

# Pydantic model for the incoming Google token
class GoogleToken(BaseModel):
    token: str

security_scheme = HTTPBearer()

# --- 2. HELPER FUNCTIONS ---

def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        raise HTTPException(status_code=500, detail="Database connection error.")

def assign_user_role(email: str) -> (str, str):
    link_id = None 
    role = None
    if email == 'rishithav.cs24@bitsathy.ac.in':
        role = 'admin'
    elif email.endswith('@parents.bitsathy.ac.in'):
        role = 'parent'
        link_id = email.split('@')[0].upper() # Correctly uppercased
    elif email.endswith('@bitsathy.ac.in'):
        role = 'student'
        pass
    return role, link_id

def create_access_token(user_id: str, user_role: str) -> str:
    expire = datetime.utcnow() + timedelta(days=1)
    to_encode = {
        "sub": user_id, "role": user_role,
        "iat": datetime.utcnow(), "exp": expire
    }
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

# --- 3. SECURITY DEPENDENCIES ---

def get_current_user_payload(token: str = Depends(security_scheme)) -> dict:
    try:
        payload = jwt.decode(token.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("sub") is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_current_user_id(payload: dict = Depends(get_current_user_payload)) -> str:
    return payload.get("sub")
            
def get_current_admin_user(payload: dict = Depends(get_current_user_payload)) -> str:
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admin access required")
    return payload.get("sub")

# --- 4. API ENDPOINTS ---

@router.post("/gsi_login")
async def gsi_login(request: Request, body: GoogleToken):
    # (Your gsi_login function... NO CHANGES NEEDED)
    token = body.token
    if not token:
        raise HTTPException(status_code=400, detail="No token provided")
    conn = None
    try:
        idinfo = id_token.verify_oauth2_token(
            token, google_requests.Request(), GOOGLE_CLIENT_ID
        )
        google_id = idinfo.get('sub')
        email = idinfo.get('email')
        name = idinfo.get('name')
        picture = idinfo.get('picture')
        role, link_id = assign_user_role(email)
        if role is None:
            return JSONResponse(status_code=403, content={"error": "Access denied. Email domain not allowed."})
        conn = get_db_connection()
        cur = conn.cursor()
        upsert_sql = """
            INSERT INTO users (id, email, name, picture_url, role, last_login_at, roll_no)
            VALUES (%s, %s, %s, %s, %s::user_role, NOW(), %s)
            ON CONFLICT (id) DO UPDATE SET
                email = EXCLUDED.email, name = EXCLUDED.name,
                picture_url = EXCLUDED.picture_url, role = EXCLUDED.role,
                last_login_at = NOW(),
                roll_no = COALESCE(EXCLUDED.roll_no, users.roll_no)
            RETURNING id;
        """
        cur.execute(upsert_sql, (google_id, email, name, picture, role, link_id))
        user_id_from_db = cur.fetchone()[0]
        log_sql = "INSERT INTO user_activity (user_id, action, details) VALUES (%s, 'login', %s)"
        cur.execute(log_sql, (user_id_from_db, f'{{"ip": "{request.client.host}"}}'))
        conn.commit()
        access_token = create_access_token(user_id=user_id_from_db, user_role=role)
        return JSONResponse({
            "message": "Login successful", "access_token": access_token,
            "token_type": "bearer", "role": role
        })
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Google token")
    except Exception as e:
        print(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")
    finally:
        if conn:
            cur.close()
            conn.close()

@router.get("/users")
async def get_user_list(admin_id: str = Depends(get_current_admin_user)):
    # (Your get_user_list function... NO CHANGES NEEDED)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, email, role, last_login_at FROM users")
        all_users = cur.fetchall()
        for user in all_users:
            status = "Offline"
            last_login = user.get('last_login_at')
            if last_login:
                if last_login.tzinfo is None:
                    last_login = last_login.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                if (now - last_login) < timedelta(minutes=15):
                    status = "Online"
            user['status'] = status
        return all_users
    except Exception as e:
        print(f"Error fetching user list: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch user list.")
    finally:
        if conn:
            cur.close()
            conn.close()

@router.get("/reward-points")
async def get_parent_reward_data(payload: dict = Depends(get_current_user_payload)):
    if payload.get("role") != "parent":
        raise HTTPException(status_code=403, detail="Access forbidden: Parent role required")
    parent_id = payload.get("sub")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT roll_no FROM users WHERE id = %s", (parent_id,))
        result = cur.fetchone()
        if not result or not result['roll_no']:
            raise HTTPException(status_code=404, detail="Parent account is not linked to a student roll number.")
        student_roll_no = result['roll_no']
        
        # --- THIS QUERY IS NOW CORRECT ---
        cur.execute(
            """
            SELECT 
                roll_no, student_name, year, mentor_name, 
                cumulative_reward_points, redeemed_points, balance_points 
            FROM student_rewards 
            WHERE roll_no = %s
            """,
            (student_roll_no,)
        )
        reward_record = cur.fetchone()
        if not reward_record:
            raise HTTPException(status_code=404, detail="No reward data found for this student.")
        return reward_record
    except HTTPException as e:
        raise e 
    except Exception as e:
        print(f"Error fetching reward data: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch reward data.")
    finally:
        if conn:
            cur.close()
            conn.close()

# --- NEW ENDPOINT: Get list of all chat sessions ---
@router.get("/chat/sessions")
async def get_chat_sessions(payload: dict = Depends(get_current_user_payload)):
    user_id = payload.get("sub")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT session_id, title, created_at 
            FROM chat_sessions
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user_id,)
        )
        sessions = cur.fetchall()
        return {"sessions": sessions}
    except Exception as e:
        print(f"Error fetching chat sessions: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch chat sessions.")
    finally:
        if conn:
            cur.close()
            conn.close()

# --- MODIFIED ENDPOINT: Get history for a SPECIFIC session ---
@router.get("/chat/history/{session_id}")
async def get_chat_history(session_id: str, payload: dict = Depends(get_current_user_payload)):
    user_id = payload.get("sub")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Security check: Ensure this user owns this session
        cur.execute(
            """
            SELECT b.message 
            FROM bot_chat_history b
            JOIN chat_sessions s ON b.session_id = s.session_id
            WHERE b.session_id = %s AND s.user_id = %s
            ORDER BY b.id ASC
            """,
            (session_id, user_id)
        )
        history_records = cur.fetchall()
        
        # The 'message' column is already JSON(B), so psycopg2 returns a dict
        history_list = [record['message'] for record in history_records]
        return {"history": history_list}
    except Exception as e:
        print(f"Error fetching chat history: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch chat history.")
    finally:
        if conn:
            cur.close()
            conn.close()