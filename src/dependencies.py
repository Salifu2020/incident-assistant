# src/dependencies.py
from .ingestion import DocumentProcessor
from .querying import KnowledgeAssistant

# LAZY LOADING: Processor is created on first access to avoid loading ChromaDB/embedding model at startup
# This allows the API to start with minimal memory usage
# Options: "all-MiniLM-L6-v2" (fast, ~80MB, recommended for deployment), 
#          "all-mpnet-base-v2" (better accuracy, ~420MB),
#          "BAAI/bge-large-en-v1.5" (state-of-the-art, ~1.3GB, slower)
# Use environment variable to override, default to lighter model for smaller Docker images
import os
default_model = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
_processor_instance = None

def get_processor():
    """Get or create the DocumentProcessor instance (lazy loading).
    
    This function ensures ChromaDB and embedding models are only loaded when actually needed,
    not at application startup. This significantly reduces startup memory usage.
    """
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = DocumentProcessor(embedding_model=default_model)
    return _processor_instance

# For backward compatibility, create a proxy
class ProcessorProxy:
    """Proxy object that lazily loads the processor."""
    def __getattr__(self, name):
        return getattr(get_processor(), name)

processor = ProcessorProxy()

# Initialize LLM model (configurable via LLM_MODEL environment variable)
# Memory-efficient model options:
# - "phi3:mini" (3.8B params, ~2.3GB RAM) - Recommended: excellent quality-to-size ratio, fast inference, good for RAG
# - "llama3.2:3b" (3B params, ~2GB RAM) - Very efficient, good performance, fast responses
# - "gemma2:2b" (2B params, ~1.5GB RAM) - Smallest option, decent quality, fastest inference
# - "qwen2.5:3b" (3B params, ~2GB RAM) - Good multilingual support, efficient
# - "mistral" (7B params, ~4.1GB RAM) - Larger, more memory-intensive (previous default)
# Default to phi3:mini for optimal memory usage and performance
llm_model = os.environ.get("LLM_MODEL", "phi3:mini")

# LAZY LOADING: Assistant is created on first access to avoid loading LLM at startup
# This allows document uploads to work immediately without consuming LLM memory
# Document upload/processing only uses processor (embedding model), not assistant (LLM)
_assistant_instance = None

def get_assistant():
    """Get or create the KnowledgeAssistant instance (lazy loading).
    
    This function ensures the LLM model is only loaded when actually needed (during queries),
    not at application startup. This significantly reduces startup memory usage.
    """
    global _assistant_instance
    if _assistant_instance is None:
        # Optimized assistant with memory-conscious settings for Railway deployment
        # Memory optimizations:
        # - Reduced cache sizes to prevent memory exhaustion
        # - Disabled some LLM-heavy features to reduce Ollama calls
        # - Lowered context size to reduce memory per request
        # - Using memory-efficient LLM model (phi3:mini by default)
        _assistant_instance = KnowledgeAssistant(
            get_processor(), 
            model_name=llm_model,
            max_context_chars=2000,  # Reduced from 2500 to save memory
            enable_streaming=True,   # Enable streaming for faster perceived response
            enable_query_expansion=True,  # Enable query expansion for smarter retrieval
            enable_hybrid_search=True,  # Enable hybrid search (semantic + keyword) for better accuracy
            enable_reranking=False,  # Disabled: Multiple LLM calls per request consume too much memory
            enable_intent_classification=False,  # Disabled: Additional LLM call per query
            enable_multi_step_reasoning=False,  # Disabled: Multiple LLM calls for complex queries
            enable_learning_from_feedback=True,  # Keep: Minimal memory impact
            enable_context_summarization=False,  # Disabled: Additional LLM call consumes memory
            summarization_threshold=1.2,
            enable_confidence_scoring=True,  # Keep: Heuristic-based, no extra LLM calls
            enable_answer_verification=False,  # Disabled: Additional LLM call per answer
            enable_query_caching=True,  # Keep: Reduces redundant queries
            cache_ttl=1800,  # Reduced from 3600: Cache for 30 minutes (less memory pressure)
            cache_max_size=100  # Reduced from 1000: Maximum 100 cached queries (90% reduction)
        )
    return _assistant_instance
