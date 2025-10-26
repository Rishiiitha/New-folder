import os
import uuid
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PyPDF2 import PdfReader
from sqlalchemy import create_engine

from langchain_postgres import PGVector
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

# --- CONFIGURATION ---
DB_URL = "postgresql+psycopg2://postgres:Veeraragava@localhost:5432/Api_input"
COLLECTION_NAME = "docs"

# Create SQLAlchemy engine
engine = create_engine(DB_URL)

# Embedding model
embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

# PGVector (new syntax)
from langchain_postgres import PGVector

VECTOR_DB = PGVector(
    connection=DB_URL,  # Your PostgreSQL URL, e.g. "postgresql://user:password@localhost:5432/dbname"
    embeddings=embedding_model,
    collection_name=COLLECTION_NAME,
)


# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- FASTAPI SETUP ---
app = FastAPI(title="Admin Document API", version="2.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- HELPERS ---
def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from a PDF file."""
    text = ""
    with open(file_path, "rb") as f:
        reader = PdfReader(f)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text
    return text


# --- ROUTES ---

@app.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    """Upload PDF and embed chunks into PGVector."""
    try:
        os.makedirs("uploads", exist_ok=True)
        file_path = os.path.join("uploads", file.filename)

        # Save file
        with open(file_path, "wb") as f:
            f.write(await file.read())

        text = extract_text_from_pdf(file_path)
        if not text.strip():
            raise HTTPException(status_code=400, detail="No readable text in PDF")

        # Split text
        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        chunks = splitter.split_text(text)

        documents = [
            Document(
                page_content=chunk,
                metadata={
                    "source": file.filename,
                    "chunk_id": str(uuid.uuid4()),
                },
            )
            for chunk in chunks
        ]

        VECTOR_DB.add_documents(documents)
        return {"message": f"Uploaded {len(chunks)} chunks from {file.filename}"}

    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/list/")
async def list_documents():
    """List all stored document filenames."""
    try:
        docs = VECTOR_DB.similarity_search(" ", k=1000)
        filenames = sorted(list({doc.metadata.get("source") for doc in docs if doc.metadata.get("source")}))
        return {"documents": filenames}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/search/")
async def search_documents(query: str):
    """Search similar chunks."""
    try:
        results = VECTOR_DB.similarity_search(query, k=5)
        return [
            {
                "source": doc.metadata.get("source"),
                "preview": doc.page_content[:250],
            }
            for doc in results
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/delete/{filename}")
async def delete_document(filename: str):
    """Delete all chunks of a specific file."""
    try:
        docs = VECTOR_DB.similarity_search(filename, k=500)
        chunk_ids = [doc.metadata.get("chunk_id") for doc in docs if doc.metadata.get("source") == filename]

        if not chunk_ids:
            return {"message": f"No records found for '{filename}'"}

        VECTOR_DB.delete(ids=chunk_ids)
        return {"message": f"Deleted {len(chunk_ids)} chunks for '{filename}'"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/delete_collection/")
async def delete_collection():
    """Delete the entire collection."""
    try:
        VECTOR_DB.delete_collection()
        return {"message": "Entire collection deleted successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
