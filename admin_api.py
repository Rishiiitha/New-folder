# admin_api.py
import os
import uuid
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGVector
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
import psycopg2
import shutil

app = FastAPI(title="PDF Upload + Vector DB Example")

# ---------------- CONFIG ----------------
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# PostgreSQL connection (update credentials)
DB_CONN = psycopg2.connect(
    dbname="Api_input",
    user="postgres",
    password="Veeraragava",   # use your actual password
    host="localhost",
    port=5432
)


# Embeddings model
EMBEDDINGS = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

# Initialize PGVector
VECTOR_DB = PGVector(
    table_name="documents",
    embedding_function=EMBEDDINGS,
    client=DB_CONN
)

# ---------------- HELPERS ----------------
def save_upload_file(upload_file: UploadFile, destination: str) -> str:
    """Save uploaded file and return its path."""
    file_id = str(uuid.uuid4())
    file_path = os.path.join(destination, f"{file_id}_{upload_file.filename}")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
    return file_path

def load_pdf(file_path: str) -> list[Document]:
    """Convert PDF into LangChain Documents."""
    from PyPDF2 import PdfReader

    reader = PdfReader(file_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"

    # Split into chunks
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100
    )
    chunks = splitter.split_text(text)
    docs = [Document(page_content=chunk) for chunk in chunks]
    return docs

# ---------------- ENDPOINT ----------------
@app.post("/upload/")
async def upload_file(
    file: UploadFile = File(...),
    url: str = Form(None),
    directory: str = Form(None)
):
    try:
        # Save file
        file_path = save_upload_file(file, UPLOAD_DIR)

        # Load PDF and create embeddings
        docs = load_pdf(file_path)

        # Add to vector DB
        VECTOR_DB.add_documents(docs)

        return JSONResponse({"status": "success", "uploaded_file": file.filename, "chunks_added": len(docs)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
