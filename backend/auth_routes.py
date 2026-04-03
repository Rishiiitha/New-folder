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

load_dotenv()
router = APIRouter()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
JWT_SECRET = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"


DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")

class GoogleToken(BaseModel):
    token: str

security_scheme = HTTPBearer()

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
        link_id = email.split('@')[0].upper() 
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



# In backend/auth_routes.py

@router.post("/gsi_login")
async def gsi_login(request: Request, body: GoogleToken):
    """
    Handles the Google Sign-In (GSI) credential from the frontend.
    Verifies the token, upserts the user, and returns our internal JWT.
    """
    token = body.token
    if not token:
        raise HTTPException(status_code=400, detail="No token provided")

    conn = None
    try:
        # 1. Verify the Google-issued token
        idinfo = id_token.verify_oauth2_token(
            token, google_requests.Request(), GOOGLE_CLIENT_ID
        )

        google_id = idinfo.get('sub')
        email = idinfo.get('email').lower() # <-- Ensure email is lowercase
        name = idinfo.get('name')
        picture = idinfo.get('picture')

        # 3. Connect to PostgreSQL
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor) # Use RealDictCursor

        # 2. Assign role and link_id
        role, link_id = assign_user_role(email)
        if role is None:
            return JSONResponse(status_code=403, content={"error": "Access denied. Email domain not allowed."})

        # --- *** NEW LOGIC: FIND STUDENT ROLL_NO *** ---
        if role == 'student':
            # This is a student. Try to find their roll number in the new table.
            cur.execute("SELECT roll_no FROM student_directory WHERE email = %s", (email,))
            student_dir_result = cur.fetchone()
            
            if student_dir_result and student_dir_result['roll_no']:
                link_id = student_dir_result['roll_no'] # This is the roll_no
                print(f"Student {email} logged in, found roll_no: {link_id}")
            else:
                print(f"Student {email} logged in, but not found in directory.")
        # --- *** END OF NEW LOGIC *** ---
        
        # 4. "REAL-TIME" DB UPDATE (UPSERT)
        # (This SQL is unchanged, but 'link_id' is now populated for students)
        upsert_sql = """
            INSERT INTO users (id, email, name, picture_url, role, last_login_at, roll_no)
            VALUES (%s, %s, %s, %s, %s::user_role, NOW(), %s)
            ON CONFLICT (id) DO UPDATE SET
                email = EXCLUDED.email,
                name = EXCLUDED.name,
                picture_url = EXCLUDED.picture_url,
                role = EXCLUDED.role,
                last_login_at = NOW(),
                roll_no = COALESCE(EXCLUDED.roll_no, users.roll_no)
            RETURNING id;
        """
        cur.execute(upsert_sql, (google_id, email, name, picture, role, link_id))
        user_id_from_db = cur.fetchone()['id']

        # 5. Log the login activity
        log_sql = "INSERT INTO user_activity (user_id, action, details) VALUES (%s, 'login', %s)"
        cur.execute(log_sql, (user_id_from_db, f'{{"ip": "{request.client.host}"}}'))

        conn.commit()
        
        # 6. Create *our* internal session token (JWT)
        access_token = create_access_token(user_id=user_id_from_db, user_role=role)
        
        # 7. Send our token and the role back to the frontend
        return JSONResponse({
            "message": "Login successful",
            "access_token": access_token,
            "token_type": "bearer",
            "role": role
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

#
# --- THIS IS THE CORRECTED FUNCTION ---
#
# In backend/auth_routes.py

@router.get("/reward-points")
async def get_reward_data(payload: dict = Depends(get_current_user_payload)):
    """
    Fetches the student's reward points.
    This endpoint now works for BOTH parents and students.
    """
    
    # --- THIS IS THE FIX ---
    # 1. Allow both 'parent' and 'student' roles
    user_role = payload.get("role")
    if user_role not in ["parent", "student"]:
        raise HTTPException(status_code=403, detail="Access forbidden: Parent or Student role required")
    # --- END OF FIX ---

    user_id = payload.get("sub") # This is the user's Google ID
    conn = None
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # 2. Get the user's roll_no (which you saved in the users table)
        cur.execute("SELECT roll_no FROM users WHERE id = %s", (user_id,))
        result = cur.fetchone()
        
        if not result or not result['roll_no']:
            raise HTTPException(status_code=404, detail="User account is not linked to a student roll number.")

        student_roll_no = result['roll_no'] # This works for both parents and students

        # 3. Find the student's reward data
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

@router.get("/chat/history/{session_id}")
async def get_chat_history(session_id: str, payload: dict = Depends(get_current_user_payload)):
    user_id = payload.get("sub")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
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
        
        history_list = [record['message'] for record in history_records]
        return {"history": history_list}
    except Exception as e:
        print(f"Error fetching chat history: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch chat history.")
    finally:
        if conn:
            cur.close()
            conn.close()