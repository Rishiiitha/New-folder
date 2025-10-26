import os
import requests
import logging
import uuid
from bs4 import BeautifulSoup
from langchain_postgres import PGVector
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 1. CONFIGURATION ---

# These MUST match your basic_bot.py
DB_CONNECTION_STRING = "postgresql+psycopg://postgres:Veeraragava@localhost:5432/Knowledge_base"
COLLECTION_NAME = "New_embeddings"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Your list of websites
WEBSITE_LIST = [
    "https://www.bitsathy.ac.in",
    "https://www.bitsathy.ac.in/chairman-desk/",
    "https://www.bitsathy.ac.in/principals-desk/",
    "https://www.bitsathy.ac.in/governing-council/",
    "https://www.bitsathy.ac.in/vision-mission/",
    "https://www.bitsathy.ac.in/milestones/",
    "https://www.bitsathy.ac.in/achievement/",
    "https://www.bitsathy.ac.in/department/",
    "https://www.bitsathy.ac.in/programmes-offered/",
    "https://www.bitsathy.ac.in/coecorner/",
    "https://www.bitsathy.ac.in/learning-centre/",
    "https://www.bitsathy.ac.in/elcc/",
    "https://www.bitsathy.ac.in/capability-enhancement-schemes/",
    "https://www.bitsathy.ac.in/admissions/",
    "https://www.bitsathy.ac.in/career-development/",
    "https://www.bitsathy.ac.in/clubs-societies/",
    "https://www.bitsathy.ac.in/campus-facilities/",
    "https://www.bitsathy.ac.in/sports-facilities/",
    "https://www.bitsathy.ac.in/college-bus-facility/",
    "https://www.bitsathy.ac.in/hostel-medical-facilities/",
    "https://www.bitsathy.ac.in/sustainability-green-initiatives/",
    "https://www.bitsathy.ac.in/community-radio/",
    "https://www.bitsathy.ac.in/event-gallery/",
    "https://www.bitsathy.ac.in/research-advisory-board/",
    "https://www.bitsathy.ac.in/research-facilities/",
    "https://www.bitsathy.ac.in/quality-improvement-programme/",
    "https://www.bitsathy.ac.in/research-contact/",
    "https://www.bitsathy.ac.in/product-innovation-centre/",
    "https://www.bitsathy.ac.in/gurugulam/",
    "https://www.bitsathy.ac.in/achievements/",
    "https://www.bitsathy.ac.in/departments/faculty/"
]

# --- 2. INITIALIZE COMPONENTS ---

logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)


try:
    store = PGVector(
        connection=DB_CONNECTION_STRING,
        collection_name=COLLECTION_NAME,
        embeddings=embeddings,
    )
    logger.info("Vector store connected.")
except Exception as e:
    logger.error(f"Failed to connect to vector store: {e}")
    exit()
    

# Initialize the text splitter
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
    separators=["\n\n", "\n", " ", ""]
)

# --- 3. INGESTION FUNCTIONS ---

def scrape_website(url: str) -> Document:
    """Scrapes a website and returns a LangChain Document."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'lxml')
        
        for script_or_style in soup(["script", "style", "nav", "footer", "header"]):
            script_or_style.decompose()
            
        content = soup.get_text(separator=' ', strip=True)
        
        if not content:
            logger.warning(f"No content extracted from {url}")
            return None

        # Create a LangChain Document
        return Document(
            page_content=content,
            metadata={
                "source": url,
                "title": soup.title.string if soup.title else "No Title"
            }
        )
    except Exception as e:
        logger.error(f"Error scraping {url}: {e}")
        return None

# --- 4. MAIN EXECUTION ---

if __name__ == "__main__":
    
    all_documents = []
    
    logger.info(f"--- Starting to process {len(WEBSITE_LIST)} websites ---")
    for url in WEBSITE_LIST:
        logger.info(f"Scraping: {url}")
        doc = scrape_website(url)
        if doc:
            all_documents.append(doc)

    if not all_documents:
        logger.error("No documents were successfully scraped. Exiting.")
        exit()

    logger.info(f"Total documents scraped: {len(all_documents)}")
    
    logger.info("Splitting documents into chunks...")
    all_chunks = text_splitter.split_documents(all_documents)
    
    logger.info(f"Total chunks created: {len(all_chunks)}")
    
    if all_chunks:
        logger.info("Adding chunks to the vector store... (This may take a while)")
        try:
            # This automatically handles embedding and batch insertion
            store.add_documents(all_chunks, ids=[str(uuid.uuid4()) for _ in all_chunks])
            logger.info("--- Ingestion complete! ---")
            
            # (Optional) Add a simple test
            logger.info("Running a quick search test...")
            results = store.similarity_search("What is the vision of the college?", k=1)
            if results:
                logger.info(f"TEST SUCCESS: Found result: {results[0].page_content[:100]}...")
            else:
                logger.warning("TEST FAILED: Search returned no results.")
                
        except Exception as e:
            logger.error(f"Failed to add documents to vector store: {e}")
    else:
        logger.warning("No chunks were created, nothing to add to the database.")