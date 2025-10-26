# filename: api.py
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableParallel, RunnablePassthrough
from langchain_ollama import OllamaLLM
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGVector

# --- 1. Setup Database Connection ---
DB_CONNECTION_STRING = "postgresql+psycopg://postgres:Veeraragava@localhost:5432/Knowledge_base"
COLLECTION_NAME = "New_embeddings"

# --- 2. Initialize Components ---
llm = OllamaLLM(model="llama3.1")
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

try:
    store = PGVector(
        connection=DB_CONNECTION_STRING,
        collection_name=COLLECTION_NAME,
        embeddings=embeddings,
    )
    retriever = store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 5}
    )
except Exception as e:
    raise RuntimeError(f"Error connecting to vector store: {e}")

# --- 3. Define Helper Functions and RAG Chain ---
def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

template = """
You are a helpful AI assistant for a college, answering questions for students and parents.
You MUST follow these rules in EVERY response:

**Rule 1: Use Context ONLY**
- Your ONLY source of information is the 'Context' provided below.
- You must ONLY answer based on the information in the 'Context'.
- **NEVER** use any of your outside general knowledge. Do not make up facts.
- If the 'Context' does not contain the information needed to answer the 'Question', you **MUST** say *exactly*: 
  "I'm sorry, I don't have that information in the college database. Please ask another question."

**Rule 2: Format for Voice (Text-to-Speech)**
- **NEVER** use bullet points, asterisks (*), lists, or any markdown formatting.
- You must write everything as a single, natural paragraph, as if you are speaking.
- You must spell out acronyms. For example, if you see 'BIT', you must write 'B I T'. If you see 'VTU', you must write 'V T U'.
- You must read phone numbers digit by digit. For example, '9876543210' must be written as 'nine eight seven six five four three two one zero'.

**Rule 3: Be Concise**
- **Keep your answers short and conversational.**
- Do not provide extra details unless the user asks for them.
- Get straight to the point.

---
Context:
{context}

Question:
{question}

Answer:
"""
prompt = ChatPromptTemplate.from_template(template)

rag_chain = (
    RunnableParallel(
        context=(retriever | format_docs),
        question=RunnablePassthrough()
    )
    | prompt
    | llm
    | StrOutputParser()
)

# --- 4. FastAPI Setup ---
app = FastAPI(title="College RAG Chatbot API")

class QueryRequest(BaseModel):
    question: str

filler_inputs = {
    "ok": "Got it. Do you have another question?",
    "okay": "Got it. Do you have another question?",
    "thanks": "You're welcome! Is there anything else I can help with?",
    "thank you": "You're welcome! Is there anything else I can help with?",
    "got it": "Great. Let me know if you have any other questions."
}

@app.post("/ask")
async def ask_question(request: QueryRequest):
    query = request.question.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    
    clean_query = query.lower().strip(" .!")
    if clean_query in filler_inputs:
        return {"answer": filler_inputs[clean_query]}
    
    try:
        answer = "".join(rag_chain.stream(query))
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
