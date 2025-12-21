# src/dependencies.py
from .ingestion import DocumentProcessor
from .querying import KnowledgeAssistant

# Initialize processor with embedding model
# Options: "all-MiniLM-L6-v2" (fast, ~80MB, recommended for deployment), 
#          "all-mpnet-base-v2" (better accuracy, ~420MB),
#          "BAAI/bge-large-en-v1.5" (state-of-the-art, ~1.3GB, slower)
# Use environment variable to override, default to lighter model for smaller Docker images
import os
default_model = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
processor = DocumentProcessor(embedding_model=default_model)
# Optimized assistant with memory-conscious settings for Railway deployment
# Memory optimizations:
# - Reduced cache sizes to prevent memory exhaustion
# - Disabled some LLM-heavy features to reduce Ollama calls
# - Lowered context size to reduce memory per request
assistant = KnowledgeAssistant(
    processor, 
    model_name="mistral",
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
