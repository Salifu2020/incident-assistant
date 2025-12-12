# src/dependencies.py
from .ingestion import DocumentProcessor
from .querying import KnowledgeAssistant

processor = DocumentProcessor()
# Optimized assistant with faster settings
assistant = KnowledgeAssistant(
    processor, 
    model_name="mistral",
    max_context_chars=2500,  # Reduced for faster processing
    enable_streaming=True     # Enable streaming for faster perceived response
)
