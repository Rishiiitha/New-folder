# filename: api_bot.py
import os
import psycopg2
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langchain_core.runnables import RunnableParallel, RunnableLambda, RunnablePassthrough
from langchain_ollama import OllamaLLM
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGVector
from dotenv import load_dotenv

# --- IMPORTS ---
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import PostgresChatMessageHistory
from auth_routes import get_current_user_id
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage # For history processing
from typing import List, Tuple, Optional

# --- Load Environment Variables ---
load_dotenv()

# --- Database Config ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "your_db_name")
DB_USER = os.getenv("DB_USER", "your_db_user")
DB_PASS = os.getenv("DB_PASS", "your_db_password")
# THE CORRECTED LINE:
DB_CONNECTION_STRING = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:5432/{DB_NAME}"
# --- LangChain & Vector Store Setup ---
llm = OllamaLLM(model="llama3.1") # Main LLM
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

# Store 1: RAG Documents
COLLECTION_NAME_DOCS = "New_embeddings"
try:
    doc_store = PGVector(connection=DB_CONNECTION_STRING, collection_name=COLLECTION_NAME_DOCS, embeddings=embeddings)
    doc_retriever = doc_store.as_retriever(search_type="similarity", search_kwargs={"k": 3})
except Exception as e:
    raise RuntimeError(f"Error connecting to RAG vector store: {e}")

# Store 2: User Profile Memory
COLLECTION_NAME_PREFS = "user_preferences"
try:
    preference_store = PGVector(connection=DB_CONNECTION_STRING, collection_name=COLLECTION_NAME_PREFS, embeddings=embeddings)
    preference_retriever = preference_store.as_retriever(search_type="similarity", search_kwargs={"k": 2})
except Exception as e:
    raise RuntimeError(f"Error connecting to preferences vector store: {e}")

# --- Helper Functions ---
def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

# --- ADVANCED: Chain 1: Chat History Summarizer ---
# Takes previous messages and condenses them
summarizer_prompt = ChatPromptTemplate.from_messages([
    MessagesPlaceholder(variable_name="chat_history"),
    ("user", "Concisely summarize the key points of the conversation above. Focus on user statements, requests, and preferences mentioned. If the history is short or empty, just say 'No summary yet'.")
])
summarization_chain = summarizer_prompt | llm | StrOutputParser()

# --- ADVANCED: Chain 2: Preference Extractor ---
# Takes the latest Q&A and extracts facts to save
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
# Prompt now accepts {summarized_history}
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
# Input: {"question": "...", "history": [<BaseMessage>], "user_id": "..."}
# Output: Final answer string

def retrieve_and_format_preferences(input_dict):
    """Retrieves preferences filtered by user_id and formats them."""
    user_id = input_dict['user_id']
    question = input_dict['question']
    # Create a retriever specifically filtered for this user
    user_pref_retriever = preference_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 2},
        filter={"user_id": user_id} # Filter metadata
    )
    docs = user_pref_retriever.invoke(question)
    return format_docs(docs)

rag_chain_core = (
    RunnableParallel(
        # 1. Get RAG context
        context=(RunnableLambda(lambda x: x['question']) | doc_retriever | format_docs),
        # 2. Get User Preferences (Filtered)
        preferences=RunnableLambda(retrieve_and_format_preferences),
        # 3. Summarize History
        summarized_history=(RunnableLambda(lambda x: {"chat_history": x['history']}) | summarization_chain),
        # 4. Pass through question
        question=RunnableLambda(lambda x: x['question'])
    )
    | prompt
    | llm
    | StrOutputParser()
)

# --- Memory Wrapper ---
# Note: RunnableWithMessageHistory expects raw message objects for history
def get_session_history(session_id: str):
   return PostgresChatMessageHistory(
        connection_string=DB_CONNECTION_STRING,  # <-- This is the fix
        session_id=session_id,
        table_name="bot_chat_history"
    )

# This chain handles loading/saving the raw chat history
chain_with_chat_history = RunnableWithMessageHistory(
    rag_chain_core, # Use the core chain that takes history objects
    get_session_history,
    input_messages_key="question",
    history_messages_key="history", # Key for raw message objects
    input_keys=["question", "user_id"], # Pass user_id through
)

# --- FastAPI Router ---
router = APIRouter()

class QueryRequest(BaseModel):
    question: str

filler_inputs = {
    # ... (same as before) ...
}

# --- Modified API Endpoint ---
@router.post("/ask")
async def ask_question(
    request: QueryRequest,
    user_id: str = Depends(get_current_user_id)
):
    query = request.question.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    clean_query = query.lower().strip(" .!")

    # Handle filler inputs (same as before)
    if clean_query in filler_inputs:
        answer = filler_inputs[clean_query]
        try:
            history = get_session_history(user_id)
            history.add_user_message(query)
            history.add_ai_message(answer)
        except Exception as e:
            print(f"Error saving filler chat to history: {e}")
        return {"answer": answer}

    # Handle RAG chain query
    try:
        # Input includes user_id now
        input_data = {"question": query, "user_id": user_id}
        config = {"configurable": {"session_id": user_id}}

        # Get the final answer (history is automatically managed)
        final_answer = chain_with_chat_history.invoke(input_data, config=config)

        # --- ADVANCED: Extract and Save Preference ---
        try:
            preference_result = preference_extraction_chain.invoke({
                "question": query,
                "answer": final_answer,
                "format_instructions": extractor_parser.get_format_instructions()
            })
            
            if preference_result and preference_result.get("fact"):
                fact = preference_result["fact"]
                print(f"Learned new fact for user {user_id}: {fact}")
                # Save the extracted fact to the preference store
                pref_doc = Document(
                    page_content=fact,
                    metadata={"user_id": user_id} # Link fact to the user
                )
                preference_store.add_documents([pref_doc])

        except Exception as extraction_err:
            # Don't fail the main response if extraction fails
            print(f"Error during preference extraction: {extraction_err}")

        return {"answer": final_answer}

    except Exception as e:
        print(f"Error in RAG chain: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")