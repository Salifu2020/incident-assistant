# app/dependencies.py
from ingestion import DocumentProcessor
from querying import KnowledgeAssistant

processor = DocumentProcessor()
assistant = KnowledgeAssistant(processor, model_name="mistral")
