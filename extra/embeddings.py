import os
import logging
from typing import List, Dict, Any, Optional, Union
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import psycopg2
from psycopg2.extras import RealDictCursor
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, AutoModel
import torch
import hashlib
import json
from datetime import datetime
import uuid
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PostgreSQLVectorStore:
    """
    A comprehensive vector store implementation using PostgreSQL with pgvector extension
    for storing and managing embeddings for RAG applications.
    """
    
    def __init__(self, 
                 postgres_url: str,
                 table_name: str = "embeddings",
                 embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
                 chunk_size: int = 1000,
                 chunk_overlap: int = 200,
                 use_llama_embedding: bool = False,
                 llama_model_path: str = None):
        """
        Initialize PostgreSQL Vector Store
        
        Args:
            postgres_url: PostgreSQL connection string
            table_name: Name of the table to store embeddings
            embedding_model: Sentence transformer model name or Llama model path
            chunk_size: Size of text chunks for processing
            chunk_overlap: Overlap between chunks
            use_llama_embedding: Whether to use Llama 3.1 compatible embedding
            llama_model_path: Path to Llama model for embeddings
        """
        self.postgres_url = postgres_url
        self.table_name = table_name
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.use_llama_embedding = use_llama_embedding
        
        # Initialize embedding model
        if use_llama_embedding:
            logger.info("Loading Llama 3.1 compatible embedding model")
            self._load_llama_embedding_model(llama_model_path or embedding_model)
        else:
            logger.info(f"Loading sentence transformer model: {embedding_model}")
            self.embedding_model = SentenceTransformer(embedding_model)
            self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
        
        # Initialize database connection
        self.engine = create_engine(postgres_url)
        self.Session = sessionmaker(bind=self.engine)
        
        # Create table if it doesn't exist
        self._create_table()
    
    def _load_llama_embedding_model(self, model_path: str):
        """Load Llama 3.1 compatible embedding model"""
        try:
            # Load tokenizer and model
            self.tokenizer = AutoTokenizer.from_pretrained(model_path)
            self.embedding_model = AutoModel.from_pretrained(
                model_path,
                torch_dtype=torch.float32,  # Use float32 for compatibility
                device_map="auto" if torch.cuda.is_available() else "cpu"
            )
            
            # Get embedding dimension from model config
            self.embedding_dim = self.embedding_model.config.hidden_size
            
            # Set padding token if not exists
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            
            logger.info(f"Loaded Llama model with embedding dimension: {self.embedding_dim}")
            
        except Exception as e:
            logger.error(f"Error loading Llama model: {e}")
            # Fallback to sentence transformer
            logger.info("Falling back to sentence transformer model")
            self.embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
            self.use_llama_embedding = False
        
    def _create_table(self):
        """Create the embeddings table with pgvector support"""
        create_table_sql = f"""
        CREATE EXTENSION IF NOT EXISTS vector;
        
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            embedding vector({self.embedding_dim}),
            metadata JSONB,
            source TEXT,
            chunk_index INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS {self.table_name}_embedding_idx 
        ON {self.table_name} USING ivfflat (embedding vector_cosine_ops);
        
        CREATE INDEX IF NOT EXISTS {self.table_name}_source_idx 
        ON {self.table_name} (source);
        
        CREATE INDEX IF NOT EXISTS {self.table_name}_metadata_idx 
        ON {self.table_name} USING gin (metadata);
        """
        
        try:
            with self.engine.connect() as conn:
                conn.execute(text(create_table_sql))
                conn.commit()
            logger.info(f"Table {self.table_name} created successfully")
        except Exception as e:
            logger.error(f"Error creating table: {e}")
            raise
    
    def _chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks"""
        if len(text) <= self.chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + self.chunk_size
            
            # Try to break at sentence boundary
            if end < len(text):
                # Look for sentence endings
                for i in range(end, max(start, end - 100), -1):
                    if text[i] in '.!?':
                        end = i + 1
                        break
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            # Move start position with overlap
            start = end - self.chunk_overlap
            if start >= len(text):
                break
                
        return chunks
    
    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a single text using Llama 3.1 compatible format"""
        try:
            if self.use_llama_embedding:
                # Tokenize input
                inputs = self.tokenizer(
                    text, 
                    return_tensors="pt", 
                    padding=True, 
                    truncation=True, 
                    max_length=512
                )
                
                # Move to same device as model
                device = next(self.embedding_model.parameters()).device
                inputs = {k: v.to(device) for k, v in inputs.items()}
                
                # Generate embeddings
                with torch.no_grad():
                    outputs = self.embedding_model(**inputs)
                    # Use mean pooling of last hidden states
                    embeddings = outputs.last_hidden_state.mean(dim=1)
                    # Convert to CPU and numpy array
                    embedding = embeddings.cpu().numpy().flatten()
                    
                # Ensure float32 format for Llama 3.1 compatibility
                return embedding.astype(np.float32).tolist()
            else:
                # Use sentence transformer
                embedding = self.embedding_model.encode(text, convert_to_tensor=False)
                # Ensure float32 format
                return embedding.astype(np.float32).tolist()
                
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise
    
    def _generate_id(self, content: str, source: str = None) -> str:
        """Generate unique ID for content"""
        content_hash = hashlib.md5(content.encode()).hexdigest()
        if source:
            return f"{source}_{content_hash}"
        return content_hash
    
    def add_text(self, 
                 content_str: str, 
                 source: str = None, 
                 metadata: Dict[str, Any] = None) -> List[str]:
        """
        Add text data to the vector store
        
        Args:
            content_str: Text content to add
            source: Source identifier for the text
            metadata: Additional metadata
            
        Returns:
            List of IDs of added embeddings
        """
        try:
            chunks = self._chunk_text(content_str)
            added_ids = []
            
            for i, chunk in enumerate(chunks):
                # Generate embedding
                embedding = self._generate_embedding(chunk)
                
                # Prepare metadata
                chunk_metadata = metadata or {}
                chunk_metadata.update({
                    'chunk_size': len(chunk),
                    'total_chunks': len(chunks),
                    'chunk_index': i
                })
                
                # Generate unique ID
                chunk_id = self._generate_id(chunk, source)
                
                # Insert into database
                insert_sql = f"""
                INSERT INTO {self.table_name} 
                (id, content, embedding, metadata, source, chunk_index)
                VALUES (:id, :content, :embedding, :metadata, :source, :chunk_index)
                ON CONFLICT (id) DO UPDATE SET
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
                """
                
                with self.engine.connect() as conn:
                    conn.execute(text(insert_sql), {
                        'id': chunk_id,
                        'content': chunk,
                        'embedding': embedding,
                        'metadata': json.dumps(chunk_metadata),
                        'source': source,
                        'chunk_index': i
                    })
                    conn.commit()
                
                added_ids.append(chunk_id)
                logger.info(f"Added chunk {i+1}/{len(chunks)} from source: {source}")
            
            logger.info(f"Successfully added {len(added_ids)} chunks to vector store")
            return added_ids
            
        except Exception as e:
            logger.error(f"Error adding text: {e}")
            raise
    
    def add_documents(self, 
                     documents: List[Dict[str, Any]], 
                     source_field: str = 'source',
                     content_field: str = 'content',
                     metadata_field: str = 'metadata') -> List[str]:
        """
        Add multiple documents to the vector store
        
        Args:
            documents: List of document dictionaries
            source_field: Field name containing source information
            content_field: Field name containing text content
            metadata_field: Field name containing metadata
            
        Returns:
            List of all added IDs
        """
        all_ids = []
        
        for doc in documents:
            try:
                content = doc.get(content_field, '')
                source = doc.get(source_field, f"doc_{len(all_ids)}")
                metadata = doc.get(metadata_field, {})
                
                if content:
                    ids = self.add_text(content, source, metadata)
                    all_ids.extend(ids)
                else:
                    logger.warning(f"Skipping document with empty content: {source}")
                    
            except Exception as e:
                logger.error(f"Error processing document {source}: {e}")
                continue
        
        return all_ids
    
    def add_file(self, 
                 file_path: str, 
                 source: str = None,
                 metadata: Dict[str, Any] = None) -> List[str]:
        """
        Add content from a file to the vector store
        
        Args:
            file_path: Path to the file
            source: Source identifier (defaults to filename)
            metadata: Additional metadata
            
        Returns:
            List of IDs of added embeddings
        """
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")
            
            source = source or os.path.basename(file_path)
            
            # Read file content based on extension
            file_ext = os.path.splitext(file_path)[1].lower()
            
            if file_ext == '.txt':
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            elif file_ext == '.csv':
                df = pd.read_csv(file_path)
                content = df.to_string()
            elif file_ext == '.json':
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    content = json.dumps(data, indent=2)
            
            # --- NEW PDF HANDLING BLOCK ---
            elif file_ext == '.pdf':
                try:
                    reader = PdfReader(file_path)
                    content_parts = []
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            content_parts.append(page_text)
                    content = "\n".join(content_parts)
                    if not content:
                        logger.warning(f"No text extracted from PDF: {file_path}")
                        return []
                except Exception as e:
                    logger.error(f"Error reading PDF {file_path}: {e}")
                    raise
            # --- END OF NEW BLOCK ---
            
            else:
                # Try to read as text
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            
            # Add file metadata
            file_metadata = metadata or {}
            file_metadata.update({
                'file_path': file_path,
                'file_size': os.path.getsize(file_path),
                'file_extension': file_ext,
                'processed_at': datetime.now().isoformat()
            })
            
            return self.add_text(content, source, file_metadata) # <-- Make sure this uses your renamed variable from before
            # If you still have 'content' as the argument name, use self.add_text(content_str=content, ...)
            
        except Exception as e:
            logger.error(f"Error adding file {file_path}: {e}")
            raise
    
    def add_directory(self, 
                     directory_path: str,
                     file_extensions: List[str] = None,
                     recursive: bool = True) -> List[str]:
        """
        Add all files from a directory to the vector store
        
        Args:
            directory_path: Path to the directory
            file_extensions: List of file extensions to include
            recursive: Whether to process subdirectories
            
        Returns:
            List of all added IDs
        """
        if file_extensions is None:
            file_extensions = ['.txt', '.csv', '.json', '.md', '.py', '.js', '.html', '.xml']
        
        all_ids = []
        
        try:
            if recursive:
                for root, dirs, files in os.walk(directory_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        if any(file.endswith(ext) for ext in file_extensions):
                            try:
                                ids = self.add_file(file_path)
                                all_ids.extend(ids)
                            except Exception as e:
                                logger.error(f"Error processing file {file_path}: {e}")
                                continue
            else:
                for file in os.listdir(directory_path):
                    file_path = os.path.join(directory_path, file)
                    if os.path.isfile(file_path) and any(file.endswith(ext) for ext in file_extensions):
                        try:
                            ids = self.add_file(file_path)
                            all_ids.extend(ids)
                        except Exception as e:
                            logger.error(f"Error processing file {file_path}: {e}")
                            continue
            
            logger.info(f"Processed directory {directory_path}, added {len(all_ids)} chunks")
            return all_ids
            
        except Exception as e:
            logger.error(f"Error processing directory {directory_path}: {e}")
            raise
    
    def add_website(self, 
                    url: str, 
                    source: str = None,
                    metadata: Dict[str, Any] = None) -> List[str]:
        """
        Add content from a website URL to the vector store
        
        Args:
            url: The website URL to scrape
            source: Source identifier (defaults to the URL)
            metadata: Additional metadata
            
        Returns:
            List of IDs of added embeddings
        """
        source = source or url
        logger.info(f"Adding website content from: {url}")
        try:
            response = requests.get(url)
            response.raise_for_status()  # Raise an error for bad responses
            
            # Use BeautifulSoup to parse HTML and get text
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Remove scripts, styles, and other non-text elements
            for script_or_style in soup(["script", "style", "nav", "footer", "header"]):
                script_or_style.decompose()
            
            content = soup.get_text(separator=' ', strip=True)
            
            if not content:
                logger.warning(f"No content extracted from {url}")
                return []

            # Add website metadata
            web_metadata = metadata or {}
            web_metadata.update({
                'url': url,
                'title': soup.title.string if soup.title else 'No Title',
                'processed_at': datetime.now().isoformat()
            })
            
            # Use the correct argument name for your add_text method
            # If you renamed it to content_str, use that.
            return self.add_text(content_str=content, source=source, metadata=web_metadata)
            
        except Exception as e:
            logger.error(f"Error adding website {url}: {e}")
            raise

    def search_similar(self, 
                      query: str, 
                      top_k: int = 5,
                      similarity_threshold: float = 0.0,
                      source_filter: str = None) -> List[Dict[str, Any]]:
        """
        Search for similar content using vector similarity
        
        Args:
            query: Search query
            top_k: Number of results to return
            similarity_threshold: Minimum similarity score
            source_filter: Filter by source
            
        Returns:
            List of similar documents with scores
        """
        try:
            # Generate query embedding
            query_embedding = self._generate_embedding(query)
            
            # Build search query
            search_sql = f"""
            SELECT 
                id,
                content,
                metadata,
                source,
                chunk_index,
                created_at,
                1 - (embedding <=> :query_embedding) as similarity_score
            FROM {self.table_name}
            WHERE 1 - (embedding <=> :query_embedding) >= :threshold
            """
            
            params = {
            'query_embedding': str(query_embedding),  # <-- Convert the list to a string
            'threshold': similarity_threshold
            }
            
            if source_filter:
                search_sql += " AND source = :source_filter"
                params['source_filter'] = source_filter
            
            search_sql += f" ORDER BY similarity_score DESC LIMIT :top_k"
            params['top_k'] = top_k
            
            with self.engine.connect() as conn:
                result = conn.execute(text(search_sql), params)
                rows = result.fetchall()
                
                results = []
                for row in rows:
                    results.append({
                        'id': row[0],
                        'content': row[1],
                        'metadata': row[2] if row[2] else {},
                        'source': row[3],
                        'chunk_index': row[4],
                        'created_at': row[5],
                        'similarity_score': float(row[6])
                    })
                
                return results
                
        except Exception as e:
            logger.error(f"Error searching: {e}")
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the vector store"""
        try:
            stats_sql = f"""
            SELECT 
                COUNT(*) as total_chunks,
                COUNT(DISTINCT source) as unique_sources,
                AVG(LENGTH(content)) as avg_content_length,
                MIN(created_at) as oldest_entry,
                MAX(created_at) as newest_entry
            FROM {self.table_name}
            """
            
            with self.engine.connect() as conn:
                result = conn.execute(text(stats_sql))
                row = result.fetchone()
                
                return {
                    'total_chunks': row[0],
                    'unique_sources': row[1],
                    'avg_content_length': float(row[2]) if row[2] else 0,
                    'oldest_entry': row[3],
                    'newest_entry': row[4],
                    'embedding_dimension': self.embedding_dim
                }
                
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            raise
    
    def delete_by_source(self, source: str) -> int:
        """Delete all embeddings from a specific source"""
        try:
            delete_sql = f"DELETE FROM {self.table_name} WHERE source = :source"
            
            with self.engine.connect() as conn:
                result = conn.execute(text(delete_sql), {'source': source})
                conn.commit()
                deleted_count = result.rowcount
                
            logger.info(f"Deleted {deleted_count} chunks from source: {source}")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error deleting by source: {e}")
            raise
    
    def clear_all(self) -> int:
        """Clear all embeddings from the vector store"""
        try:
            delete_sql = f"DELETE FROM {self.table_name}"
            
            with self.engine.connect() as conn:
                result = conn.execute(text(delete_sql))
                conn.commit()
                deleted_count = result.rowcount
                
            logger.info(f"Cleared {deleted_count} chunks from vector store")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error clearing vector store: {e}")
            raise


# Example usage and utility functions
def create_vector_store(postgres_url: str, 
                       table_name: str = "embeddings",
                       embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
                       use_llama: bool = False,
                       llama_model_path: str = None) -> PostgreSQLVectorStore:
    """
    Create a new PostgreSQL vector store instance
    
    Args:
        postgres_url: PostgreSQL connection string
        table_name: Name of the table to store embeddings
        embedding_model: Sentence transformer model name or Llama model path
        use_llama: Whether to use Llama 3.1 compatible embedding
        llama_model_path: Path to Llama model (e.g., "meta-llama/Llama-3.1-8B-Instruct")
        
    Returns:
        PostgreSQLVectorStore instance
    """
    return PostgreSQLVectorStore(
        postgres_url, 
        table_name, 
        embedding_model,
        use_llama_embedding=use_llama,
        llama_model_path=llama_model_path
    )


def batch_process_data(data_sources: List[Union[str, Dict]], 
                      vector_store: PostgreSQLVectorStore) -> Dict[str, Any]:
    """
    Batch process multiple data sources into the vector store
    
    Args:
        data_sources: List of file paths, directories, or document dictionaries
        vector_store: PostgreSQLVectorStore instance
        
    Returns:
        Processing summary
    """
    results = {
        'processed': 0,
        'failed': 0,
        'total_chunks': 0,
        'errors': []
    }
    
    for source in data_sources:
        try:
            if isinstance(source, str):
                if os.path.isfile(source):
                    ids = vector_store.add_file(source)
                    results['processed'] += 1
                    results['total_chunks'] += len(ids)
                elif os.path.isdir(source):
                    ids = vector_store.add_directory(source)
                    results['processed'] += 1
                    results['total_chunks'] += len(ids)
                else:
                    # Treat as text content
                    ids = vector_store.add_text(source)
                    results['processed'] += 1
                    results['total_chunks'] += len(ids)
            elif isinstance(source, dict):
                ids = vector_store.add_text(
                    source.get('content', ''),
                    source.get('source'),
                    source.get('metadata')
                )
                results['processed'] += 1
                results['total_chunks'] += len(ids)
                
        except Exception as e:
            results['failed'] += 1
            results['errors'].append(f"Error processing {source}: {str(e)}")
            logger.error(f"Error processing {source}: {e}")
    
    return results


if __name__ == "__main__":
    
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

    # --- Connect to your local DB ---
    # (Make sure this URL is correct for your local setup)
    POSTGRES_URL = "postgresql://postgres:Veeraragava@localhost:5432/Knowledge_base"
    
    # Use the standard vector store (table_name="embeddings")
    vs_standard = create_vector_store(POSTGRES_URL, table_name="embeddings")
    print("--- Connected to Standard Vector Store ---")

    
    # --- Loop through and add all websites ---
    print(f"--- Starting to process {len(WEBSITE_LIST)} websites ---")
    
    for url in WEBSITE_LIST:
        try:
            # We use the URL itself as the 'source' for easy tracking
            vs_standard.add_website(url, source=url)
        except Exception as e:
            # This makes sure that if one URL fails, the script continues
            print(f"!!! FAILED to process {url}: {e} !!!")
            continue # Move to the next URL
    
    print("--- Website processing complete ---")

        
    # --- Search for your new data ---
    
    print("\n--- Example Search: 'vision and mission' ---")
    results = vs_standard.search_similar("What is the vision and mission of the college?", top_k=2)
    for result in results:
        print(f"Score: {result['similarity_score']:.3f} - (Source: {result['source']})")
        print(f"Content: {result['content'][:200]}...\n")

    print(f"\n--- Final Stats ---")
    print(vs_standard.get_stats())