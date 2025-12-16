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
    language: Optional[str] = None  # User's preferred language code (e.g., 'en', 'es', 'fr', 'de', 'it', 'pt', 'zh', 'ja', 'ko', 'ar', 'ru', 'hi')

class QueryIntent(BaseModel):
    intent: str  # factual, how_to, definition, comparison, list, explanation, verification, follow_up
    confidence: float  # Confidence score 0.0-1.0

class ConfidenceScore(BaseModel):
    confidence: float  # Confidence score 0.0-1.0
    level: str  # "high", "medium", "low", "very_low"
    factors: Optional[Dict] = None  # Breakdown of confidence factors

class AnswerVerification(BaseModel):
    status: str  # "supported", "partial", "unsupported", "not_verified", "error"
    supported: bool  # Whether answer is fully supported by context
    details: str  # Explanation of verification result
    has_hallucinations: bool  # Whether answer contains unsupported information

class AnswerVerification(BaseModel):
    status: str  # "supported", "partial", "unsupported", "not_verified", "error"
    supported: bool  # Whether answer is fully supported by context
    details: str  # Explanation of verification result
    has_hallucinations: bool  # Whether answer contains unsupported information

class QuestionResponse(BaseModel):
    response: str
    sources: List[SourceCitation] = []
    intent: Optional[QueryIntent] = None  # Query intent classification result
    confidence: Optional[ConfidenceScore] = None  # Answer confidence score
    verification: Optional[AnswerVerification] = None  # Answer verification result
    verification: Optional[AnswerVerification] = None  # Answer verification result

class UploadResponse(BaseModel):
    message: str

class BulkUploadRequest(BaseModel):
    filenames: List[str]  # List of filenames to upload from source_files directory

class BulkUploadResponse(BaseModel):
    total_files: int
    successful: int
    failed: int
    results: List[Dict]  # List of {filename, status, message, chunks_added}

class BatchDeleteRequest(BaseModel):
    filenames: List[str]  # List of document filenames to delete

class BatchDeleteResponse(BaseModel):
    total_files: int
    successful: int
    failed: int
    total_chunks_deleted: int
    results: List[Dict]  # List of {filename, status, message, chunks_deleted}

class BulkReprocessRequest(BaseModel):
    filenames: Optional[List[str]] = None  # If None, reprocess all documents

class BulkReprocessResponse(BaseModel):
    total_files: int
    successful: int
    failed: int
    results: List[Dict]  # List of {filename, status, message, chunks_added}

class OperationProgress(BaseModel):
    operation_id: str
    operation_type: str  # "upload", "delete", "reprocess"
    total_items: int
    completed_items: int
    failed_items: int
    current_item: Optional[str] = None
    status: str  # "running", "completed", "failed"
    results: List[Dict] = []

class DocumentInfo(BaseModel):
    filename: str
    file_type: str
    chunk_count: int
    upload_date: Optional[str] = None
    file_size: Optional[int] = None
    file_path: Optional[str] = None
    version: Optional[int] = None
    version_count: Optional[int] = None

class DocumentVersion(BaseModel):
    version: int
    file_path: str
    file_hash: str
    file_size: int
    uploaded_by: Dict[str, str]
    uploaded_at: str
    is_current: bool

class DocumentVersionInfo(BaseModel):
    filename: str
    versions: List[DocumentVersion]
    current_version: int
    created_at: str
    updated_at: str

class RestoreVersionRequest(BaseModel):
    version: int

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

class ResponseTimeStats(BaseModel):
    min: float
    max: float
    avg: float
    p50: float
    p95: float
    p99: float

class QueryStats(BaseModel):
    total: int
    last_hour: int
    last_6_hours: int
    throughput_per_hour: float
    response_time: ResponseTimeStats
    avg_sources_per_query: float

class ErrorStats(BaseModel):
    total: int
    rate_percent: float
    by_type: Dict[str, int]

class DocumentProcessingStats(BaseModel):
    total_processed: int
    successful: int
    failed: int
    success_rate_percent: float
    avg_processing_time_sec: float
    avg_chunks_per_doc: float
    total_size_bytes: int
    total_size_mb: float

class PerformanceStats(BaseModel):
    period_hours: int
    timestamp: str
    queries: QueryStats
    errors: ErrorStats
    document_processing: DocumentProcessingStats

class PerformanceStatsResponse(BaseModel):
    stats: PerformanceStats

# Authentication Models
class UserRegister(BaseModel):
    username: str
    email: str
    password: str
    role: Optional[str] = "user"

class UserLogin(BaseModel):
    username: str
    password: str

class UserInfo(BaseModel):
    id: str
    username: str
    email: str
    role: str
    created_at: Optional[str] = None
    last_login: Optional[str] = None
    active: Optional[bool] = True
    locked: Optional[bool] = False
    unlock_time: Optional[str] = None
    failed_attempts: Optional[int] = 0
    password_expires_at: Optional[str] = None
    password_expired: Optional[bool] = False
    twofa_enabled: Optional[bool] = False
    display_name: Optional[str] = None
    bio: Optional[str] = None
    avatar: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo
    refresh_token: Optional[str] = None
    session_id: Optional[str] = None
    requires_2fa: Optional[bool] = False

class TokenData(BaseModel):
    username: Optional[str] = None
    user_id: Optional[str] = None
    role: Optional[str] = None

class UserListResponse(BaseModel):
    users: List[UserInfo]
    total: int

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class UpdateUserRoleRequest(BaseModel):
    user_id: str
    role: str

class PasswordResetRequest(BaseModel):
    email: str

class PasswordResetVerifyRequest(BaseModel):
    token: str

class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str

class PasswordResetResponse(BaseModel):
    message: str
    token: Optional[str] = None

class TwoFASetupResponse(BaseModel):
    secret: str
    qr_code_uri: str
    backup_codes: List[str]

class TwoFAVerifyRequest(BaseModel):
    code: str

class TwoFALoginRequest(BaseModel):
    code: str

class TwoFAResponse(BaseModel):
    message: str
    backup_codes: Optional[List[str]] = None

class SessionInfo(BaseModel):
    session_id: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    device_info: Optional[str] = None
    created_at: str
    last_activity: str
    is_current: bool = False

class SessionListResponse(BaseModel):
    sessions: List[SessionInfo]
    total: int

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class TokenRefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class AuditLogEntry(BaseModel):
    timestamp: str
    event_type: str
    user_id: Optional[str] = None
    username: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    details: Optional[Dict] = None

class AuditLogResponse(BaseModel):
    logs: List[AuditLogEntry]
    total: int
    filtered_total: Optional[int] = None

class AuditLogFilter(BaseModel):
    event_type: Optional[str] = None
    username: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    limit: Optional[int] = 100  # For development/testing - remove in production

class UserPreferences(BaseModel):
    theme: Optional[str] = "light"  # light, dark, auto
    notifications_enabled: Optional[bool] = True
    email_notifications: Optional[bool] = True
    language: Optional[str] = "en"
    default_settings: Optional[Dict] = None

class ProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    bio: Optional[str] = None

class PreferencesUpdateRequest(BaseModel):
    theme: Optional[str] = None
    notifications_enabled: Optional[bool] = None
    email_notifications: Optional[bool] = None
    language: Optional[str] = None
    default_settings: Optional[Dict] = None

class ProfileResponse(BaseModel):
    user: UserInfo
    preferences: UserPreferences

# Analytics Models
class QueryAnalyticsEntry(BaseModel):
    query: str
    count: int
    pattern_data: Optional[Dict] = None

class DocumentUsageEntry(BaseModel):
    document: str
    query_count: int
    last_accessed: Optional[str] = None

class IntentPerformance(BaseModel):
    avg_response_time: float
    query_count: int

class ConfidenceStats(BaseModel):
    avg: float
    min: float
    max: float
    high_confidence_count: int
    low_confidence_count: int
    total_with_confidence: int

class CachePerformance(BaseModel):
    hits: int
    misses: int
    hit_rate: float

class VerificationStats(BaseModel):
    total_verified: int
    supported_count: int
    partial_count: int
    unsupported_count: int
    not_verified_count: int
    by_status: Dict[str, int]

class QueryTrendEntry(BaseModel):
    hour: str
    count: int

class QueryAnalyticsResponse(BaseModel):
    period_hours: int
    total_queries: int
    most_asked_queries: List[QueryAnalyticsEntry]
    document_usage: List[DocumentUsageEntry]
    intent_distribution: Dict[str, int]
    intent_performance: Dict[str, IntentPerformance]
    confidence_stats: Optional[ConfidenceStats] = None
    cache_performance: CachePerformance
    query_trends: List[QueryTrendEntry]
    verification_stats: VerificationStats

class KnowledgeGap(BaseModel):
    intent: str
    query_count: int
    avg_confidence: float
    sample_queries: List[str]
    recommendation: str

class KnowledgeGapsResponse(BaseModel):
    gaps: List[KnowledgeGap]
    total_gaps: int

class UserActivityEntry(BaseModel):
    user_id: str
    query_count: int
    last_activity: Optional[str] = None

class UserInsightsResponse(BaseModel):
    total_active_users: int
    top_users: List[UserActivityEntry]
    total_user_queries: int
