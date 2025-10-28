import os
from jose import jwt
import psycopg2
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor  # <-- ADD THIS LINE
# Imports for Google GSI token verification
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

# Correct import for JSONResponse
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
DB_NAME = os.getenv("DB_NAME", "your_db_name")
DB_USER = os.getenv("DB_USER", "your_db_user")
DB_PASS = os.getenv("DB_PASS", "your_db_password")

# Pydantic model for the incoming Google token
class GoogleToken(BaseModel):
    token: str

# Define the security scheme
security_scheme = HTTPBearer()


# --- 2. HELPER FUNCTIONS ---

def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
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
    """
    Assigns a role and extracts the link_id (roll_no).
    Based on your screenshot:
    - Parent: '7376241cs343@parents.bitsathy.ac.in' -> link_id = '7376241cs343'
    - Student: 'rishithav.cs24@bitsathy.ac.in' -> link_id = None
    Returns: (role, link_id)
    """
    link_id = None  # This will be stored in the 'roll_no' column
    role = None

    if email == 'rishithav.cs24@bitsathy.ac.in':
        role = 'admin'
    elif email.endswith('@parents.bitsathy.ac.in'):
        role = 'parent'
        link_id = email.split('@')[0].upper()  # Extracts the ID from parent's email
    elif email.endswith('@bitsathy.ac.in'):
        role = 'student'
        # Per your clarification, we can't get the ID from the student's email.
        # It must be set manually by an admin in the database.
        pass
    
    return role, link_id

def create_access_token(user_id: str, user_role: str) -> str:
    """Generates our internal JWT for the user session."""
    expire = datetime.utcnow() + timedelta(days=1)
    to_encode = {
        "sub": user_id,    # The user's unique Google ID
        "role": user_role, # 'admin', 'parent', or 'student'
        "iat": datetime.utcnow(),
        "exp": expire
    }
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt


# --- 3. SECURITY DEPENDENCIES ---
# These functions are used to protect your API endpoints.
# Your other files (apibot.py, ingest.py) will import these.

def get_current_user_payload(token: str = Depends(security_scheme)) -> dict:
    """
    Validates the JWT and returns the full payload.
    This is the base dependency.
    """
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
    """
    For endpoints that just need a valid user (like the chatbot).
    Used by: api_bot.py
    """
    return payload.get("sub")
            
def get_current_admin_user(payload: dict = Depends(get_current_user_payload)) -> str:
    """
    For endpoints that require ADMIN access.
    Used by: ingest.py (all routes) and /users (in this file)
    """
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admin access required")
    return payload.get("sub")


# --- 4. API ENDPOINTS ---

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
        email = idinfo.get('email')
        name = idinfo.get('name')
        picture = idinfo.get('picture')

        # 2. Assign role and link_id
        role, link_id = assign_user_role(email)
        if role is None:
            return JSONResponse(status_code=403, content={"error": "Access denied. Email domain not allowed."})

        # 3. Connect to PostgreSQL
        conn = get_db_connection()
        cur = conn.cursor()

        # 4. "REAL-TIME" DB UPDATE (UPSERT)
        upsert_sql = """
            INSERT INTO users (id, email, name, picture_url, role, last_login_at, roll_no)
            VALUES (%s, %s, %s, %s, %s::user_role, NOW(), %s)
            ON CONFLICT (id) DO UPDATE SET
                email = EXCLUDED.email,
                name = EXCLUDED.name,
                picture_url = EXCLUDED.picture_url,
                role = EXCLUDED.role,
                last_login_at = NOW(),
                -- Only update roll_no if the new value is NOT NULL
                -- This prevents a student login from overwriting a manually set roll_no
                roll_no = COALESCE(EXCLUDED.roll_no, users.roll_no)
            RETURNING id;
        """
        cur.execute(upsert_sql, (google_id, email, name, picture, role, link_id))
        user_id_from_db = cur.fetchone()[0]

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
        # This catches invalid Google tokens
        raise HTTPException(status_code=401, detail="Invalid Google token")
    except Exception as e:
        print(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")
    finally:
        if conn:
            cur.close()
            conn.close()


@router.get("/my-students")
async def get_my_students(payload: dict = Depends(get_current_user_payload)):
    """
    Fetches the student(s) linked to a parent's account.
    This NOW fetches REAL data from the student_academics table.
    """
    # 1. Ensure user is a parent
    if payload.get("role") != "parent":
        raise HTTPException(status_code=403, detail="Access forbidden: Parent role required")

    parent_id = payload.get("sub")
    conn = None
    
    try:
        conn = get_db_connection()
        # Use RealDictCursor to get results as dictionaries
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # 2. Get the parent's "link_id" (which is the student's roll_no)
        cur.execute("SELECT roll_no FROM users WHERE id = %s", (parent_id,))
        result = cur.fetchone()
        
        if not result or not result['roll_no']:
            return []  # This parent has no link_id, so no students

        student_roll_no = result['roll_no']  # This is the unique ID (e.g., '7376241cs343')

        # 3. Find the student's academic data from the 'student_academics' table
        # This REPLACES your old dummy data logic
        cur.execute(
            "SELECT roll_no, name, email, attendance, cgpa, fees_pending FROM student_academics WHERE roll_no = %s",
            (student_roll_no,)
        )
        student_record = cur.fetchone()  # .fetchone() because roll_no is unique

        if not student_record:
            return []  # No academic record found for this roll_no

        # 4. Return the data in a list, as the frontend expects
        # The 'student_record' is already a dictionary thanks to RealDictCursor
        return [student_record]

    except Exception as e:
        print(f"Error fetching students: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch student data.")
    finally:
        if conn:
            cur.close()
            conn.close()

@router.get("/users")
async def get_user_list(admin_id: str = Depends(get_current_admin_user)):
    """
    Fetches all users from the database.
    Only accessible by admins.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get all users
        cur.execute("SELECT id, email, role, last_login_at FROM users")
        all_users = cur.fetchall()
        
        users_list = []
        for user in all_users:
            user_id, email, role, last_login = user
            
            # Determine "Online" status (e.g., logged in last 15 mins)
            status = "Offline"
            if last_login:
                if last_login.tzinfo is None:
                    last_login = last_login.replace(tzinfo=timezone.utc)
                
                now = datetime.now(timezone.utc)
                if (now - last_login) < timedelta(minutes=15):
                    status = "Online"
                    
            users_list.append({
                "id": user_id,
                "email": email,
                "role": role,
                "status": status
            })
            
        return users_list

    except HTTPException as e:
        raise e # Re-raise security exceptions
    except Exception as e:
        print(f"Error fetching user list: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch user list.")
    finally:
        if conn:
            cur.close()
            conn.close()

# In auth_routes.py

# ... (at the end of the file, after your @router.get("/users") function) ...

@router.get("/reward-points")
async def get_parent_reward_data(payload: dict = Depends(get_current_user_payload)):
    """
    Fetches the student's reward points (from the CSV data)
    linked to a parent's account.
    """
    # 1. Ensure user is a parent
    if payload.get("role") != "parent":
        raise HTTPException(status_code=403, detail="Access forbidden: Parent role required")

    parent_id = payload.get("sub")
    conn = None
    
    try:
        conn = get_db_connection()
        # Use RealDictCursor to get results as dictionaries
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # 2. Get the parent's "link_id" (which is the student's roll_no)
        cur.execute("SELECT roll_no FROM users WHERE id = %s", (parent_id,))
        result = cur.fetchone()
        
        if not result or not result['roll_no']:
            # This parent has no link_id, so no student
            raise HTTPException(status_code=404, detail="Parent account is not linked to a student roll number.")

        student_roll_no = result['roll_no']

        # 3. Find the student's reward data from the 'student_rewards' table
        cur.execute(
            """
            SELECT roll_no, student_name, year,mentor_name,
                   cumulative_reward_points, redeemed_points, balance_points 
            FROM student_rewards 
            WHERE roll_no = %s
            """,
            (student_roll_no,)
        )
        reward_record = cur.fetchone() # .fetchone() because roll_no is unique

        if not reward_record:
            raise HTTPException(status_code=404, detail="No reward data found for this student.")

        # 4. Return the data (it's already a dictionary)
        return reward_record

    except HTTPException as e:
        raise e # Re-raise HTTP exceptions
    except Exception as e:
        print(f"Error fetching reward data: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch reward data.")
    finally:
        if conn:
            cur.close()
            conn.close()

# In auth_routes.py

# ... (at the very bottom, after your /auth/reward-points endpoint) ...

@router.get("/chat/history")
async def get_chat_history(payload: dict = Depends(get_current_user_payload)):
    """
    Fetches the user's entire chat history, ordered by time.
    """
    user_id = payload.get("sub") # This is the Google 'sub' ID
    conn = None
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # --- THIS IS THE CORRECT QUERY ---
        cur.execute(
            """
            SELECT message FROM bot_chat_history
            WHERE session_id = %s
            ORDER BY id ASC
            """,
            (user_id,) # Use the Google sub ID as the session_id
        )
        history_records = cur.fetchall()
        
        # --- THIS IS THE FIX for the text/JSON bug ---
        # Parse the 'message' string from each row into real JSON
        history_list = [(record['message']) for record in history_records]
        
        return {"history": history_list}

    except Exception as e:
        print(f"Error fetching chat history: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch chat history.")
    finally:
        if conn:
            cur.close()
            conn.close()