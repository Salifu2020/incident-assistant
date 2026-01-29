"""
Vector Store abstraction layer.
Supports multiple backends: pgvector (Supabase/Postgres), ChromaDB (local).
"""
import os
import logging
import hashlib
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class VectorStore(ABC):
    """Abstract base class for vector stores."""
    
    @abstractmethod
    def add_documents(self, documents: List[str], metadatas: List[Dict], ids: List[str]) -> None:
        """Add documents with their embeddings to the store."""
        pass
    
    @abstractmethod
    def query(self, query_text: str, n_results: int = 5, 
              where: Dict = None) -> Dict[str, List]:
        """Query the store for similar documents."""
        pass
    
    @abstractmethod
    def delete(self, ids: List[str] = None, where: Dict = None) -> None:
        """Delete documents from the store."""
        pass
    
    @abstractmethod
    def count(self) -> int:
        """Return the number of documents in the store."""
        pass
    
    @abstractmethod
    def get(self, ids: List[str] = None, where: Dict = None) -> Dict[str, List]:
        """Get documents by ID or filter."""
        pass


class PgVectorStore(VectorStore):
    """
    PostgreSQL with pgvector extension - works with Supabase, Neon, or any Postgres.
    
    Requires:
    - PostgreSQL with pgvector extension enabled
    - DATABASE_URL environment variable
    """
    
    def __init__(self, connection_string: str = None, 
                 embedding_model: str = "all-MiniLM-L6-v2",
                 table_name: str = "documents",
                 embedding_dimension: int = 384):
        """
        Initialize pgvector store.
        
        Args:
            connection_string: Database URL (defaults to DATABASE_URL env var)
            embedding_model: SentenceTransformer model for embeddings
            table_name: Name of the table to store documents
            embedding_dimension: Dimension of embeddings (384 for MiniLM, 768 for mpnet)
        """
        self.connection_string = connection_string or os.environ.get("DATABASE_URL")
        self.table_name = table_name
        self.embedding_dimension = embedding_dimension
        self._embedding_model_name = embedding_model
        self._embedding_model = None
        self._engine = None
        self._initialized = False
        
        if not self.connection_string:
            raise ValueError("DATABASE_URL environment variable not set")
        
        # Normalize connection string for SQLAlchemy
        if self.connection_string.startswith("postgresql://"):
            self.connection_string = self.connection_string.replace(
                "postgresql://", "postgresql+psycopg2://", 1
            )
    
    @property
    def embedding_model(self):
        """Lazy-load embedding model."""
        if self._embedding_model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"🔤 Loading embedding model: {self._embedding_model_name}")
            self._embedding_model = SentenceTransformer(self._embedding_model_name)
            logger.info(f"✅ Embedding model loaded")
        return self._embedding_model
    
    @property
    def engine(self):
        """Lazy-load database engine."""
        if self._engine is None:
            from sqlalchemy import create_engine
            self._engine = create_engine(
                self.connection_string,
                pool_pre_ping=True,
                pool_recycle=300
            )
        return self._engine
    
    def _init_table(self):
        """Initialize the documents table with pgvector."""
        if self._initialized:
            return
        
        from sqlalchemy import text
        
        with self.engine.connect() as conn:
            # Enable pgvector extension
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            
            # Create documents table
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    embedding vector({self.embedding_dimension}),
                    metadata JSONB DEFAULT '{{}}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # Create index for faster similarity search
            conn.execute(text(f"""
                CREATE INDEX IF NOT EXISTS {self.table_name}_embedding_idx 
                ON {self.table_name} 
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
            """))
            
            conn.commit()
            
        self._initialized = True
        logger.info(f"✅ pgvector table '{self.table_name}' initialized")
    
    def _get_embedding(self, text: str) -> List[float]:
        """Get embedding for a text."""
        return self.embedding_model.encode(text).tolist()
    
    def _get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for multiple texts."""
        return self.embedding_model.encode(texts).tolist()
    
    def add_documents(self, documents: List[str], metadatas: List[Dict], ids: List[str]) -> None:
        """Add documents with their embeddings."""
        self._init_table()
        
        from sqlalchemy import text
        import json
        
        # Generate embeddings in batch
        embeddings = self._get_embeddings(documents)
        
        with self.engine.connect() as conn:
            for doc, metadata, doc_id, embedding in zip(documents, metadatas, ids, embeddings):
                # Upsert document
                conn.execute(text(f"""
                    INSERT INTO {self.table_name} (id, content, embedding, metadata)
                    VALUES (:id, :content, :embedding, :metadata)
                    ON CONFLICT (id) DO UPDATE SET
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata
                """), {
                    "id": doc_id,
                    "content": doc,
                    "embedding": str(embedding),
                    "metadata": json.dumps(metadata)
                })
            conn.commit()
        
        logger.info(f"✅ Added {len(documents)} documents to pgvector")
    
    def query(self, query_text: str, n_results: int = 5, 
              where: Dict = None) -> Dict[str, List]:
        """Query for similar documents."""
        self._init_table()
        
        from sqlalchemy import text
        import json
        
        # Get query embedding
        query_embedding = self._get_embedding(query_text)
        
        # Build WHERE clause
        where_clause = ""
        params = {
            "embedding": str(query_embedding),
            "limit": n_results
        }
        
        if where:
            conditions = []
            for i, (key, value) in enumerate(where.items()):
                param_name = f"where_{i}"
                if isinstance(value, dict) and "$in" in value:
                    # Handle $in operator
                    conditions.append(f"metadata->>'{key}' = ANY(:where_{i})")
                    params[param_name] = value["$in"]
                else:
                    conditions.append(f"metadata->>'{key}' = :where_{i}")
                    params[param_name] = value
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)
        
        with self.engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT id, content, metadata, 
                       1 - (embedding <=> :embedding) as similarity
                FROM {self.table_name}
                {where_clause}
                ORDER BY embedding <=> :embedding
                LIMIT :limit
            """), params)
            
            rows = result.fetchall()
        
        # Format results to match ChromaDB interface
        return {
            "ids": [[row[0] for row in rows]],
            "documents": [[row[1] for row in rows]],
            "metadatas": [[json.loads(row[2]) if isinstance(row[2], str) else row[2] for row in rows]],
            "distances": [[1 - row[3] for row in rows]]  # Convert similarity to distance
        }
    
    def delete(self, ids: List[str] = None, where: Dict = None) -> None:
        """Delete documents."""
        self._init_table()
        
        from sqlalchemy import text
        
        with self.engine.connect() as conn:
            if ids:
                conn.execute(text(f"""
                    DELETE FROM {self.table_name} WHERE id = ANY(:ids)
                """), {"ids": ids})
            elif where:
                # Build WHERE clause for metadata
                conditions = []
                params = {}
                for i, (key, value) in enumerate(where.items()):
                    param_name = f"where_{i}"
                    conditions.append(f"metadata->>'{key}' = :where_{i}")
                    params[param_name] = value
                
                if conditions:
                    where_clause = " AND ".join(conditions)
                    conn.execute(text(f"""
                        DELETE FROM {self.table_name} WHERE {where_clause}
                    """), params)
            
            conn.commit()
    
    def count(self) -> int:
        """Return document count."""
        self._init_table()
        
        from sqlalchemy import text
        
        with self.engine.connect() as conn:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {self.table_name}"))
            return result.scalar()
    
    def get(self, ids: List[str] = None, where: Dict = None) -> Dict[str, List]:
        """Get documents by ID or filter."""
        self._init_table()
        
        from sqlalchemy import text
        import json
        
        params = {}
        where_clause = ""
        
        if ids:
            where_clause = "WHERE id = ANY(:ids)"
            params["ids"] = ids
        elif where:
            conditions = []
            for i, (key, value) in enumerate(where.items()):
                param_name = f"where_{i}"
                if isinstance(value, dict) and "$in" in value:
                    conditions.append(f"metadata->>'{key}' = ANY(:where_{i})")
                    params[param_name] = value["$in"]
                else:
                    conditions.append(f"metadata->>'{key}' = :where_{i}")
                    params[param_name] = value
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)
        
        with self.engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT id, content, metadata FROM {self.table_name} {where_clause}
            """), params)
            rows = result.fetchall()
        
        return {
            "ids": [row[0] for row in rows],
            "documents": [row[1] for row in rows],
            "metadatas": [json.loads(row[2]) if isinstance(row[2], str) else row[2] for row in rows]
        }


class ChromaDBStore(VectorStore):
    """
    ChromaDB vector store - Local file-based storage.
    Good for development and simple deployments.
    """
    
    def __init__(self, persist_directory: str = None, 
                 embedding_model: str = "all-MiniLM-L6-v2",
                 collection_name: str = "knowledge_base"):
        """
        Initialize ChromaDB store.
        
        Args:
            persist_directory: Directory for persistence
            embedding_model: SentenceTransformer model for embeddings
            collection_name: Name of the collection
        """
        import chromadb
        from chromadb.utils import embedding_functions
        
        # Get project root
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.persist_directory = persist_directory or os.path.join(project_root, ".chromadb")
        self._embedding_model_name = embedding_model
        self.collection_name = collection_name
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(path=self.persist_directory)
        
        # Lazy-load embedding function and collection
        self._embedding_function = None
        self._collection = None
        self._collection_initialized = False
    
    @property
    def embedding_function(self):
        """Lazy-load embedding function."""
        if self._embedding_function is None:
            from chromadb.utils import embedding_functions
            logger.info(f"🔤 Loading embedding model: {self._embedding_model_name}")
            self._embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=self._embedding_model_name
            )
            logger.info(f"✅ Embedding model loaded")
        return self._embedding_function
    
    @property
    def collection(self):
        """Lazy-load collection."""
        if not self._collection_initialized:
            try:
                # Try to get existing collection
                self._collection = self.client.get_collection(name=self.collection_name)
                logger.info(f"📂 Loaded existing '{self.collection_name}' collection")
            except:
                # Create new collection
                self._collection = self.client.get_or_create_collection(
                    name=self.collection_name,
                    embedding_function=self.embedding_function
                )
                logger.info(f"🆕 Created new '{self.collection_name}' collection")
            self._collection_initialized = True
        return self._collection
    
    def add_documents(self, documents: List[str], metadatas: List[Dict], ids: List[str]) -> None:
        """Add documents."""
        self.collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        logger.info(f"✅ Added {len(documents)} documents to ChromaDB")
    
    def query(self, query_text: str, n_results: int = 5, 
              where: Dict = None) -> Dict[str, List]:
        """Query for similar documents."""
        return self.collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where
        )
    
    def delete(self, ids: List[str] = None, where: Dict = None) -> None:
        """Delete documents."""
        if ids:
            self.collection.delete(ids=ids)
        elif where:
            self.collection.delete(where=where)
    
    def count(self) -> int:
        """Return document count."""
        return self.collection.count()
    
    def get(self, ids: List[str] = None, where: Dict = None) -> Dict[str, List]:
        """Get documents."""
        return self.collection.get(ids=ids, where=where)


def get_vector_store(store_type: str = None, embedding_model: str = None) -> VectorStore:
    """
    Factory function to get the appropriate vector store.
    
    Priority order (if store_type not specified):
    1. pgvector (if DATABASE_URL is set and VECTOR_STORE != "chromadb")
    2. ChromaDB (fallback, always available)
    
    Args:
        store_type: Explicit store type ("pgvector", "chromadb")
        embedding_model: Embedding model to use
    
    Returns:
        VectorStore instance
    """
    store_type = store_type or os.environ.get("VECTOR_STORE", "auto")
    embedding_model = embedding_model or os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    
    # Determine embedding dimension based on model
    embedding_dimensions = {
        "all-MiniLM-L6-v2": 384,
        "all-mpnet-base-v2": 768,
        "BAAI/bge-large-en-v1.5": 1024,
    }
    embedding_dim = embedding_dimensions.get(embedding_model, 384)
    
    if store_type == "pgvector" or (store_type == "auto" and os.environ.get("DATABASE_URL")):
        try:
            store = PgVectorStore(
                embedding_model=embedding_model,
                embedding_dimension=embedding_dim
            )
            logger.info(f"🚀 Using pgvector store (Supabase/Postgres)")
            return store
        except Exception as e:
            if store_type == "pgvector":
                raise RuntimeError(f"pgvector requested but not available: {e}")
            logger.warning(f"pgvector not available, falling back to ChromaDB: {e}")
    
    # Fallback to ChromaDB
    logger.info(f"🚀 Using ChromaDB store (local)")
    return ChromaDBStore(embedding_model=embedding_model)
