import os
import psycopg2
import uuid # <-- 1. Import UUID
from psycopg2.extras import RealDictCursor # <-- 2. Import RealDictCursor
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langchain_core.runnables import RunnableParallel, RunnableLambda, RunnablePassthrough
from langchain_ollama import OllamaLLM
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGVector
from dotenv import load_dotenv
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import PostgresChatMessageHistory
from auth_routes import get_current_user_id
from langchain_core.documents import Document
from typing import Optional

# --- Load Environment Variables ---
load_dotenv()

# --- Database Config ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "Student_data")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "Veeraragava")
DB_CONNECTION_STRING = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:5432/{DB_NAME}"

# --- LangChain & Vector Store Setup ---
llm = OllamaLLM(model="llama3.1")
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
COLLECTION_NAME_DOCS = "New_embeddings"
COLLECTION_NAME_PREFS = "user_preferences"

try:
    doc_store = PGVector(connection=DB_CONNECTION_STRING, collection_name=COLLECTION_NAME_DOCS, embeddings=embeddings)
    doc_retriever = doc_store.as_retriever(search_type="similarity", search_kwargs={"k": 3})
    
    preference_store = PGVector(connection=DB_CONNECTION_STRING, collection_name=COLLECTION_NAME_PREFS, embeddings=embeddings)
except Exception as e:
    raise RuntimeError(f"Error connecting to vector stores: {e}")

# (Your helper functions, chains, and prompts... NO CHANGES NEEDED)
# --- Helper Functions ---
def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

# --- ADVANCED: Chain 1: Chat History Summarizer ---
summarizer_prompt = ChatPromptTemplate.from_messages([
    MessagesPlaceholder(variable_name="chat_history"),
    ("user", "Concisely summarize the key points of the conversation above. Focus on user statements, requests, and preferences mentioned. If the history is short or empty, just say 'No summary yet'.")
])
summarization_chain = summarizer_prompt | llm | StrOutputParser()

# --- ADVANCED: Chain 2: Preference Extractor ---
class Preference(BaseModel):
    fact: Optional[str] = Field(description="A single, concise fact or preference learned about the user from the conversation, or null if nothing new was learned.")
extractor_parser = JsonOutputParser(pydantic_object=Preference)
extractor_prompt = ChatPromptTemplate.from_template(
    "Analyze the following user question and bot answer. Did you learn a new, specific, permanent fact or preference about the user (e.g., 'user likes dosa', 'user's name is Rishi', 'user prefers short answers')? "
    "If yes, state ONLY that single fact. If no, output null.\n\n"
    "User Question: {question}\n"
    "Bot Answer: {answer}\n\n"
    "Respond ONLY with JSON formatted according to the following schema:\n"
    "{format_instructions}"
)
preference_extraction_chain = extractor_prompt | llm | extractor_parser

# --- RAG Chain Definition (Revised Prompt) ---
template = """
You are a helpful AI assistant for a college. You MUST follow all rules.
First, here are facts and preferences about the user:
{preferences}
Here is a summary of the previous conversation:
{summarized_history}
**Rule 1: Use Context ONLY**
- Answer based ONLY on 'Context', 'History Summary', or 'User Preferences'.
- NEVER use outside general knowledge.
- If the answer isn't in your provided info, say *exactly*:
  "I'm sorry, I don't have that information. Please ask another question."
**Rule 2: Format for Voice** (Same rules as before)
- No markdown, single paragraph, spell out acronyms, read digits.
---
Context from documents:
{context}
Question:
{question}
Answer:
"""
prompt = ChatPromptTemplate.from_template(template)

# --- ADVANCED RAG Chain (Handles Summarization) ---
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

# --- Memory Wrapper ---
# This is now just a factory for the history object
def get_session_history(session_id: str):
   return PostgresChatMessageHistory(
        connection_string=DB_CONNECTION_STRING,
        session_id=session_id, # Uses the specific session_id
        table_name="bot_chat_history" # The new table
    )

chain_with_chat_history = RunnableWithMessageHistory(
    rag_chain_core,
    get_session_history,
    input_messages_key="question",
    history_messages_key="history",
    input_keys=["question", "user_id"],
)

# --- FastAPI Router ---
router = APIRouter()

class QueryRequest(BaseModel):
    question: str
    session_id: Optional[str] = None # <-- 3. Expect a session_id

filler_inputs = {
    # (same as before) ...
}

# --- 4. Database Helper for Session Management ---
def get_db_conn_for_api():
    # This is a simple connection for use *inside* API endpoints
    try:
        conn = psycopg2.connect(
            host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS
        )
        return conn
    except Exception as e:
        print(f"API DB Connection Error: {e}")
        return None

# --- 5. HEAVILY MODIFIED API Endpoint ---
@router.post("/ask")
async def ask_question(
    request: QueryRequest,
    user_id: str = Depends(get_current_user_id)
):
    query = request.question.strip()
    session_id = request.session_id
    new_session_id = None # Flag to return to frontend
    
    if not query:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    conn = None
    try:
        conn = get_db_conn_for_api()
        if not conn:
            raise HTTPException(status_code=500, detail="Database connection error")
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # --- Session Creation Logic ---
        if not session_id:
            # This is a new chat
            new_session_id = str(uuid.uuid4())
            session_id = new_session_id # Use this new ID for the rest of the request
            
            # Create a title (first 50 chars of the question)
            title = query[:50] + "..." if len(query) > 50 else query
            
            cur.execute(
                "INSERT INTO chat_sessions (session_id, user_id, title) VALUES (%s, %s, %s)",
                (session_id, user_id, title)
            )
            conn.commit()
        else:
            # This is an existing chat. Verify the user owns this session.
            cur.execute(
                "SELECT * FROM chat_sessions WHERE session_id = %s AND user_id = %s",
                (session_id, user_id)
            )
            if not cur.fetchone():
                raise HTTPException(status_code=403, detail="Not authorized for this session")

        # --- Filler Input Handling (Now uses the correct session_id) ---
        clean_query = query.lower().strip(" .!")
        if clean_query in filler_inputs:
            answer = filler_inputs[clean_query]
            try:
                history = get_session_history(session_id) # Use correct session_id
                history.add_user_message(query)
                history.add_ai_message(answer)
            except Exception as e:
                print(f"Error saving filler chat to history: {e}")
            return {"answer": answer, "session_id": session_id}

        # --- RAG Chain Query ---
        input_data = {"question": query, "user_id": user_id}
        config = {"configurable": {"session_id": session_id}} # Use correct session_id

        final_answer = chain_with_chat_history.invoke(input_data, config=config)
        
        # --- Preference Extraction (No changes needed, still uses user_id) ---
        try:
            preference_result = preference_extraction_chain.invoke({
                "question": query, "answer": final_answer,
                "format_instructions": extractor_parser.get_format_instructions()
            })
            if preference_result and preference_result.get("fact"):
                fact = preference_result["fact"]
                pref_doc = Document(
                    page_content=fact,
                    metadata={"user_id": user_id}
                )
                preference_store.add_documents([pref_doc])
        except Exception as extraction_err:
            print(f"Error during preference extraction: {extraction_err}")

        # Return the answer AND the session_id
        # (new_session_id will be the ID if it was just created, else None)
        return {"answer": final_answer, "new_session_id": new_session_id, "session_id": session_id}

    except HTTPException as e:
        raise e # Re-raise security exceptions
    except Exception as e:
        print(f"Error in RAG chain: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
    finally:
        if conn:
            cur.close()
            conn.close()