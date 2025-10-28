import os
import uuid
import logging
import psycopg  # For direct SQL operations
import fitz     # For PyMuPDF
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from langchain_postgres import PGVector
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from dotenv import load_dotenv

# --- IMPORT YOUR ADMIN SECURITY ---
from auth_routes import get_current_admin_user

# --- LOAD .ENV VARIABLES ---
load_dotenv()
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "your_db_name")
DB_USER = os.getenv("DB_USER", "your_db_user")
DB_PASS = os.getenv("DB_PASS", "your_db_password")

# This string is for LangChain (SQLAlchemy)
DB_CONNECTION_STRING = f"postgresql+psycopg://{DB_USER}:{DB_PASS}@{DB_HOST}:5432/{DB_NAME}"
COLLECTION_NAME = "New_embeddings" 

# --- SETUP COMPONENTS ---
# <-- NOTE: To "Refine the embedding model", you would fine-tune a model
# and change the 'model_name' here to your new model.
embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

try:
    VECTOR_DB = PGVector(
        connection=DB_CONNECTION_STRING,
        embeddings=embedding_model,
        collection_name=COLLECTION_NAME,
        pre_delete_collection=False,
    )
except Exception as e:
    print(f"Error connecting to PGVector in ingest.py: {e}")
    raise RuntimeError(e)

# --- SETUP LOGGER ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- FASTAPI ROUTER ---
router = APIRouter()

# --- HELPERS ---
# <-- MODIFIED: We removed the old `extract_text_from_pdf` helper
# as we now process the PDF page-by-page inside the upload route.

# --- ROUTES (NOW SECURED) ---
@router.post("/upload/")
async def upload_file(
    file: UploadFile = File(...),
    admin_id: str = Depends(get_current_admin_user)
):
    """
    Upload PDF, extract rich metadata, and embed chunks into PGVector.
    This implements "Leverage document structure" and "Automated metadata extraction".
    """
    try:
        os.makedirs("uploads", exist_ok=True)
        file_path = os.path.join("uploads", file.filename)

        with open(file_path, "wb") as f:
            f.write(await file.read())

        # <-- MODIFIED: Start of new structured extraction logic
        page_documents = []
        doc_metadata = {}

        try:
            with fitz.open(file_path) as doc:
                # Extract document-level metadata
                doc_metadata = doc.metadata
                
                for page_num, page in enumerate(doc.pages()):
                    page_text = page.get_text()
                    if page_text.strip(): # Only process pages with text
                        
                        # Create rich metadata for each page
                        page_meta = {
                            "source": file.filename,
                            "page_number": page_num + 1,
                            "doc_title": doc_metadata.get('title', 'N/A'),
                            "doc_author": doc_metadata.get('author', 'N/A'),
                            "doc_creation_date": doc_metadata.get('creationDate', 'N/A')
                        }
                        
                        # Create a Document object for the *entire page*
                        page_documents.append(
                            Document(
                                page_content=page_text,
                                metadata=page_meta
                            )
                        )
        except Exception as e:
            logger.error(f"Failed to process PDF {file.filename}: {e}")
            raise HTTPException(status_code=400, detail=f"Failed to process PDF: {e}")

        if not page_documents:
            raise HTTPException(status_code=400, detail="No readable text in PDF")

        # <-- MODIFIED: We now use `split_documents` on our page list
        # This is better than splitting one giant text blob.
        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        final_chunks = splitter.split_documents(page_documents)

        # Add a unique chunk_id to each chunk's metadata for deletion
        for chunk in final_chunks:
            chunk.metadata["chunk_id"] = str(uuid.uuid4())

        if final_chunks:
            VECTOR_DB.add_documents(final_chunks)

        return {
            "message": f"Uploaded {len(final_chunks)} chunks from {file.filename}",
            "document_metadata": doc_metadata
        }
        # <-- MODIFIED: End of new logic

    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/list/")
async def list_documents(admin_id: str = Depends(get_current_admin_user)):
    """List all stored document filenames efficiently via direct SQL."""
    
    sql_command = """
        SELECT DISTINCT cmetadata->>'source'
        FROM langchain_pg_embedding
        WHERE collection_id = (
            SELECT uuid FROM langchain_pg_collection WHERE name = %s
        )
    """
    
    psycopg_conn_string = DB_CONNECTION_STRING.replace("+psycopg", "")

    try:
        with psycopg.connect(psycopg_conn_string) as conn:
            with conn.cursor() as curs:
                curs.execute(sql_command, (COLLECTION_NAME,))
                results = curs.fetchall() 

        filenames = sorted([row[0] for row in results if row[0]])
        return {"documents": filenames}

    except Exception as e:
        logger.error(f"Failed to list documents with SQL: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search/")
async def search_documents(
    query: str,
    admin_id: str = Depends(get_current_admin_user)
):
    """Search similar chunks."""
    try:
        results = VECTOR_DB.similarity_search(query, k=5)
        
        # <-- RECOMMENDATION: Implement de-duplication here
        seen_content = set()
        unique_results = []
        for doc in results:
            content_preview = doc.page_content[:200] 
            if content_preview not in seen_content:
                seen_content.add(content_preview)
                unique_results.append(doc)
        
        return [
            {
                "source": doc.metadata.get("source"),
                # <-- MODIFIED: Also show new metadata in search preview
                "page": doc.metadata.get("page_number"),
                "title": doc.metadata.get("doc_title"),
                "preview": doc.page_content[:250],
            }
            for doc in unique_results # Use the de-duplicated list
        ]
    except Exception as e:
        logger.error(f"Failed to search documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/delete/{filename}")
async def delete_document(
    filename: str,
    admin_id: str = Depends(get_current_admin_user)
):
    """Delete all chunks of a specific file using a direct SQL query."""

    sql_command = """
        DELETE FROM langchain_pg_embedding
        WHERE cmetadata->>'source' = %s AND collection_id = (
            SELECT uuid FROM langchain_pg_collection WHERE name = %s
        )
    """

    psycopg_conn_string = DB_CONNECTION_STRING.replace("+psycopg", "")

    try:
        with psycopg.connect(psycopg_conn_string) as conn:
            with conn.cursor() as curs:
                curs.execute(sql_command, (filename, COLLECTION_NAME))
                count = curs.rowcount
                conn.commit()

        if count == 0:
            return {"message": f"No records found for '{filename}' in collection '{COLLECTION_NAME}'"}

        return {"message": f"Deleted {count} chunks for '{filename}'"}

    except Exception as e:
        logger.error(f"Failed to delete document with SQL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete_collection/")
async def delete_collection(admin_id: str = Depends(get_current_admin_user)):
    """
    Delete the entire collection specified by COLLECTION_NAME.
    """
    try:
        VECTOR_DB.delete_collection()
        return {"message": f"Entire collection '{COLLECTION_NAME}' deleted successfully."}
    except Exception as e:
        logger.error(f"Failed to delete collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))