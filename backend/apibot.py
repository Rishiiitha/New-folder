import os
import psycopg2
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langchain_core.runnables import RunnableParallel, RunnableLambda
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import PostgresChatMessageHistory
from langchain_ollama import OllamaLLM
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGVector
from langchain_core.documents import Document
from dotenv import load_dotenv
from typing import Optional
from twilio.rest import Client
from auth_routes import get_current_user_id  # Auth dependency

# --- Load Environment ---
load_dotenv()

# --- DB CONFIG ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "your_db_name")
DB_USER = os.getenv("DB_USER", "your_db_user")
DB_PASS = os.getenv("DB_PASS", "your_db_password")

DB_CONNECTION_STRING = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:5432/{DB_NAME}"

# --- LangChain Setup ---
llm = OllamaLLM(model="llama3.1")
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

# --- PGVector: RAG Docs ---
COLLECTION_NAME_DOCS = "New_embeddings"
doc_store = PGVector(connection=DB_CONNECTION_STRING, collection_name=COLLECTION_NAME_DOCS, embeddings=embeddings)
doc_retriever = doc_store.as_retriever(search_type="similarity", search_kwargs={"k": 3})

# --- PGVector: User Preferences ---
COLLECTION_NAME_PREFS = "user_preferences"
preference_store = PGVector(connection=DB_CONNECTION_STRING, collection_name=COLLECTION_NAME_PREFS, embeddings=embeddings)
preference_retriever = preference_store.as_retriever(search_type="similarity", search_kwargs={"k": 2})

def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

# --- Summarizer Chain ---
summarizer_prompt = ChatPromptTemplate.from_messages([
    MessagesPlaceholder(variable_name="chat_history"),
    ("user", "Summarize the conversation focusing on user questions and preferences. If none, say 'No summary yet'.")
])
summarization_chain = summarizer_prompt | llm | StrOutputParser()

# --- Preference Extractor ---
class Preference(BaseModel):
    fact: Optional[str] = Field(description="A single fact or preference learned about the user.")

extractor_parser = JsonOutputParser(pydantic_object=Preference)
extractor_prompt = ChatPromptTemplate.from_template(
    "Analyze:\nUser: {question}\nAI: {answer}\nIf a new permanent fact or preference is learned, output it. Else null.\n{format_instructions}"
)
preference_extraction_chain = extractor_prompt | llm | extractor_parser

# --- RAG Prompt ---
rag_template = """
You are a helpful AI assistant for college-related queries.

User Preferences:
{preferences}

Chat Summary:
{summarized_history}

Context:
{context}

Rules:
1. Use only the info in context, summary, or preferences.
2. If not found, reply exactly: "I'm sorry, I don't have that information. Please ask another question."
3. Format naturally (for voice).

Question:
{question}

Answer:
"""
prompt = ChatPromptTemplate.from_template(rag_template)

# --- Retrieve User Preferences ---
def retrieve_and_format_preferences(input_dict):
    user_id = input_dict['user_id']
    question = input_dict['question']
    user_pref_retriever = preference_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 2},
        filter={"user_id": user_id}
    )
    docs = user_pref_retriever.invoke(question)
    return format_docs(docs)

# --- Core RAG Chain ---
rag_chain_core = (
    RunnableParallel(
        context=(RunnableLambda(lambda x: x['question']) | doc_retriever | format_docs),
        preferences=RunnableLambda(retrieve_and_format_preferences),
        summarized_history=(RunnableLambda(lambda x: {"chat_history": x['history']}) | summarization_chain),
        question=RunnableLambda(lambda x: x['question'])
    )
    | prompt
    | llm
    | StrOutputParser()
)

# --- Chat History in Postgres ---
def get_session_history(session_id: str):
    return PostgresChatMessageHistory(
        connection_string=DB_CONNECTION_STRING,
        session_id=session_id,
        table_name="bot_chat_history"
    )

# --- Helper: Fetch username from DB ---
def get_username_from_db(user_id: str) -> str:
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        cur = conn.cursor()
        cur.execute("SELECT name FROM users WHERE id = %s", (user_id,))
        conn.commit()
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return row[0]
        return "Unknown User"
    except Exception as e:
        print(f"⚠️ Failed to fetch username: {e}")
        return "Unknown User"

# --- Twilio SMS ---
def send_sms(to_number: str, message: str):
    try:
        client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
        from_number = os.getenv("TWILIO_PHONE_NUMBER")
        client.messages.create(body=message, from_=from_number, to=to_number)
        print(f"✅ SMS sent to {to_number}: {message}")
    except Exception as e:
        print(f"⚠️ SMS sending failed: {e}")

# --- Wrap Chain with Memory ---
chain_with_chat_history = RunnableWithMessageHistory(
    rag_chain_core,
    get_session_history,
    input_messages_key="question",
    history_messages_key="history",
    input_keys=["question", "user_id"]
)

# --- FastAPI Router ---
router = APIRouter()

class QueryRequest(BaseModel):
    question: str

@router.post("/ask")
async def ask_question(request: QueryRequest, user_id: str = Depends(get_current_user_id)):
    query = request.question.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    try:
        username = get_username_from_db(user_id)
        print(f"🟢 User '{username}' asked: {query}")

        answer = chain_with_chat_history.invoke(
            {"question": query, "user_id": user_id},
            config={"configurable": {"session_id": str(user_id)}}
        )

        # --- Category detection ---
        query_lower = query.lower()

        academic_keywords = ["exam", "subject", "mark", "attendance", "result", "class", "syllabus", "faculty", "assignment", "project","teacher","absent","lecture","course","notes","tutorial","lab","semester","grade","curriculum","timetable","schedule"]
        mess_keywords = ["mess", "food", "canteen", "menu", "meal", "dining", "lunch", "breakfast", "dinner", "cafeteria", "taste", "rotten", "hygiene", "quality", "vegetarian", "non-vegetarian"]
        transport_keywords = ["bus", "transport", "shuttle", "route", "timing", "stop", "vehicle", "parking", "driver", "delay", "accident", "overspeed", "traffic", "speed", "late", "missed","ticket","schedule","station"]
        electronics_keywords = ["wifi", "wi-fi", "internet", "network", "device", "laptop", "computer", "system", "printer", "projector", "software", "hardware", "technical", "access", "connectivity", "signal", "router", "modem"]
        complaint_keywords = ["not good", "bad", "poor", "worst", "terrible", "complaint", "issue", "problem", "delay", "broken", "repair", "dirty", "smell", "late", "missed", "stuck", "cannot", "unable", "didn't reach"]

        category = "General"
        target_numbers = ["+919342236331"]

        if any(w in query_lower for w in mess_keywords):
            category = "Mess"
            target_numbers = ["+919025312830"]
        elif any(w in query_lower for w in transport_keywords):
            category = "Transport"
            target_numbers = ["+917339170590"]
        elif any(w in query_lower for w in electronics_keywords):
            category = "Electronics"
            target_numbers = ["+919363521885"]
        elif any(w in query_lower for w in academic_keywords):
            category = "Academic"
            target_numbers = ["+919342236331"]

        # --- Complaint Alert ---
        if any(w in query_lower for w in complaint_keywords):
            msg = f"⚠️ Complaint Alert ({category}): '{query}' reported by {username}."
            for num in target_numbers:
                send_sms(num, msg)

        # --- Missing Info Alert ---
        if "don't have that information" in answer.lower():
            msg = f"AI Assistant Alert: Missing info for query '{query}' (User: {username})."
            for num in target_numbers:
                send_sms(num, msg)
            return {"answer": "I'm sorry, I don't have that information."}

        return {"answer": answer}

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error: {e}")