# src/dependencies.py
from .ingestion import DocumentProcessor
from .querying import KnowledgeAssistant

processor = DocumentProcessor()
# Optimized assistant with faster settings
assistant = KnowledgeAssistant(
    processor, 
    model_name="mistral",
    max_context_chars=2500,  # Reduced for faster processing
    enable_streaming=True,   # Enable streaming for faster perceived response
    enable_query_expansion=True,  # Enable query expansion for smarter retrieval
    enable_hybrid_search=True,  # Enable hybrid search (semantic + keyword) for better accuracy
    enable_reranking=True,  # Enable re-ranking of retrieved chunks for improved relevance
    enable_intent_classification=True,  # Enable query intent classification for better responses
    enable_multi_step_reasoning=True,  # Enable multi-step reasoning for complex queries
    enable_learning_from_feedback=True,  # Enable learning from user feedback to improve over time
    enable_context_summarization=True,  # Enable context summarization for long documents
    summarization_threshold=1.2  # Summarize if context exceeds max_context_chars * 1.2
)
