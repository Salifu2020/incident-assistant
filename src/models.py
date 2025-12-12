# app/models.py
from pydantic import BaseModel
from typing import List, Optional, Dict

class SourceCitation(BaseModel):
    source: str
    relevance: float
    distance: float

class QuestionRequest(BaseModel):
    query: str
    document_filters: Optional[List[str]] = None  # List of document filenames to filter by
    conversation_id: Optional[str] = None  # Conversation ID for context

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

class QuerySuggestion(BaseModel):
    query: str
    type: str  # "saved", "history", or "popular"
    score: float
    name: Optional[str] = None
    usage_count: Optional[int] = None

class SuggestionsResponse(BaseModel):
    suggestions: List[QuerySuggestion]
    total: int

class FeedbackRequest(BaseModel):
    query: str
    response: str
    rating: int  # 1-5 for stars, -1 for thumbs down, 1 for thumbs up
    feedback_type: str = "rating"  # "rating", "thumbs", "detailed"
    comment: Optional[str] = None
    sources_count: int = 0

class FeedbackResponse(BaseModel):
    message: str
    feedback_id: Optional[str] = None

class FeedbackEntry(BaseModel):
    query: str
    response_preview: str
    rating: int
    feedback_type: str
    comment: str
    sources_count: int
    timestamp: str

class FeedbackStats(BaseModel):
    total: int
    average_rating: float
    thumbs_up: int
    thumbs_down: int
    ratings_distribution: dict
    positive_feedback: int
    negative_feedback: int

class FeedbackStatsResponse(BaseModel):
    stats: FeedbackStats

class ConversationMessage(BaseModel):
    role: str
    content: str
    sources: List[SourceCitation] = []
    timestamp: str

class Conversation(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: List[ConversationMessage] = []
    context_enabled: bool = True
    message_count: int = 0

class ConversationListResponse(BaseModel):
    conversations: List[Conversation]
    total: int

class CreateConversationRequest(BaseModel):
    title: Optional[str] = None

class UpdateConversationRequest(BaseModel):
    title: Optional[str] = None
    context_enabled: Optional[bool] = None

class AdvancedSearchFilters(BaseModel):
    """Advanced search filter options."""
    document_names: Optional[List[str]] = None  # Filter by specific documents
    file_types: Optional[List[str]] = None  # Filter by file types (pdf, docx, txt, etc.)
    date_from: Optional[str] = None  # Filter by processing date from (YYYY-MM-DD)
    date_to: Optional[str] = None  # Filter by processing date to (YYYY-MM-DD)
    min_relevance: Optional[float] = None  # Minimum relevance score (0.0-1.0)
    max_results: Optional[int] = None  # Maximum number of results to return
    exclude_documents: Optional[List[str]] = None  # Documents to exclude

class AdvancedQuestionRequest(BaseModel):
    query: str
    filters: Optional[AdvancedSearchFilters] = None
    conversation_id: Optional[str] = None

class HealthSummary(BaseModel):
    status: str
    health_score: int
    timestamp: str
    knowledge_base: Dict
    performance: Dict
    alerts: List[Dict]
    error: Optional[str] = None

class HealthResponse(BaseModel):
    health: HealthSummary

class MetricEntry(BaseModel):
    type: str
    value: float
    timestamp: str
    metadata: Dict

class MetricsHistoryResponse(BaseModel):
    metrics: List[MetricEntry]
    total: int

class PerformanceStats(BaseModel):
    total_queries: int
    total_errors: int
    total_documents_processed: int
    avg_query_time: float
    error_rate: float
    successful_documents: int

class PerformanceStatsResponse(BaseModel):
    stats: PerformanceStats
