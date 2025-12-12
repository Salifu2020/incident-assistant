# app/models.py
from pydantic import BaseModel
from typing import List, Optional

class SourceCitation(BaseModel):
    source: str
    relevance: float
    distance: float

class QuestionRequest(BaseModel):
    query: str

class QuestionResponse(BaseModel):
    response: str
    sources: List[SourceCitation] = []

class UploadResponse(BaseModel):
    message: str

class DocumentInfo(BaseModel):
    filename: str
    file_type: str
    chunk_count: int
    upload_date: Optional[str] = None
    file_size: Optional[int] = None
    file_path: Optional[str] = None

class DocumentListResponse(BaseModel):
    documents: List[DocumentInfo]
    total_documents: int
    total_chunks: int

class DeleteDocumentResponse(BaseModel):
    message: str
    deleted_chunks: int
    filename: str

class HistoryEntry(BaseModel):
    query: str
    timestamp: str
    response_length: int = 0
    sources_count: int = 0

class HistoryResponse(BaseModel):
    history: List[HistoryEntry]
    total: int

class SavedQuery(BaseModel):
    query: str
    name: str
    description: str = ""
    created_at: str
    updated_at: str
    usage_count: int = 0

class SavedQueriesResponse(BaseModel):
    saved_queries: List[SavedQuery]
    total: int

class SaveQueryRequest(BaseModel):
    query: str
    name: Optional[str] = None
    description: Optional[str] = None

class UpdateSavedQueryRequest(BaseModel):
    query: str
    name: Optional[str] = None
    description: Optional[str] = None
