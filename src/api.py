from fastapi import FastAPI, File, UploadFile, HTTPException, Request, BackgroundTasks, Depends, status, Request as FastAPIRequest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional
import os
import logging
import shutil
import json
import asyncio
import io
import zipfile
from logging.handlers import RotatingFileHandler
from datetime import timedelta, datetime
from pathlib import Path

from .dependencies import get_processor, get_assistant, processor
from . import models as _models  # For models.QueryIntent (avoids namespace issues)
from .models import (
    QuestionRequest, QuestionResponse, QueryIntent, UploadResponse,
    DocumentListResponse, DocumentInfo, DeleteDocumentResponse,
    HistoryResponse, HistoryEntry, SavedQueriesResponse, SavedQuery,
    SaveQueryRequest, UpdateSavedQueryRequest,
    SuggestionsResponse, QuerySuggestion,
    FeedbackRequest, FeedbackResponse, FeedbackEntry, FeedbackStats, FeedbackStatsResponse,
    Conversation, ConversationListResponse, ConversationMessage,
    CreateConversationRequest, UpdateConversationRequest,
    AdvancedSearchFilters, AdvancedQuestionRequest,
    ConfidenceScore, AnswerVerification,
    HealthSummary, HealthResponse, MetricEntry, MetricsHistoryResponse,
    PerformanceStats, PerformanceStatsResponse,
    UserRegister, UserLogin, UserInfo, Token, TokenData, UserListResponse,
    ChangePasswordRequest, UpdateUserRoleRequest,
    PasswordResetRequest, PasswordResetVerifyRequest, PasswordResetConfirmRequest,
    PasswordResetResponse,
    TwoFASetupResponse, TwoFAVerifyRequest, TwoFALoginRequest, TwoFAResponse,
    SessionInfo, SessionListResponse, RefreshTokenRequest, TokenRefreshResponse,
    AuditLogEntry, AuditLogResponse, AuditLogFilter,
    UserPreferences, ProfileUpdateRequest, PreferencesUpdateRequest, ProfileResponse,
    QueryAnalyticsResponse, QueryAnalyticsEntry, DocumentUsageEntry, IntentPerformance,
    ConfidenceStats, CachePerformance, VerificationStats, QueryTrendEntry,
    KnowledgeGapsResponse, KnowledgeGap, UserInsightsResponse, UserActivityEntry,
    BulkUploadRequest, BulkUploadResponse, BatchDeleteRequest, BatchDeleteResponse,
    BulkReprocessRequest, BulkReprocessResponse, OperationProgress,
    ExportRequest, ExportResponse, BackupRequest, BackupResponse, BackupInfo,
    BackupListResponse, RestoreRequest,
    ChunkingConfigRequest, ChunkingConfigResponse
)
from .history import SearchHistory, SavedQueries, QuerySuggestions, AnswerFeedback, ConversationManager
from .health import HealthMonitor
from .analytics import AnalyticsTracker
from .analytics import AnalyticsTracker
from .auth import (
    UserManager, verify_token, create_access_token, create_refresh_token,
    verify_refresh_token, create_session, update_session_activity,
    revoke_session, revoke_all_user_sessions, get_user_sessions,
    get_session_by_token, cleanup_expired_sessions, load_sessions, save_sessions,
    log_audit_event, load_audit_logs,
    SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS,
    AVATARS_DIR
)

# Initialize basic logger early for use in exception handlers
_logger = logging.getLogger(__name__)

# Try to use database-backed auth, fall back to JSON if database not available
try:
    from .database import init_db, is_db_available
    from .db_auth import DBUserManager
    _use_db = True
except ImportError:
    _use_db = False
    _logger.warning("Database modules not available, using JSON file storage")

# Helper function to get the appropriate user manager
def get_user_manager():
    """Get user manager (database if available, otherwise JSON)."""
    if _use_db and is_db_available():
        return DBUserManager
    return UserManager

# Get project root directory (parent of src)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Logging Configuration
log_dir = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(log_dir, exist_ok=True)
log_file_path = os.path.join(log_dir, "api.log")

file_handler = RotatingFileHandler(log_file_path, maxBytes=1_000_000, backupCount=3, encoding='utf-8')
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

# Create a safe StreamHandler that handles Unicode encoding errors on Windows
class SafeStreamHandler(logging.StreamHandler):
    """StreamHandler that safely handles Unicode encoding errors."""
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            # Try to write with UTF-8 encoding, fallback to ascii with error handling
            try:
                stream.write(msg + self.terminator)
            except UnicodeEncodeError:
                # If encoding fails, encode to ASCII with replacement
                stream.write(msg.encode('ascii', 'replace').decode('ascii') + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)

stream_handler = SafeStreamHandler()
stream_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[stream_handler, file_handler],
)

# Update logger reference after logging is configured
logger = _logger

# Import email service (optional - will work without it) - Must be after logger definition
try:
    from .email_service import EmailService
except ImportError:
    EmailService = None
    logger.warning("Email service not available. Install aiosmtplib, email-validator, and jinja2 for email support.")

app = FastAPI(title="Knowledge Assistant API")

# Allow CORS (adjust for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add response compression for better performance
app.add_middleware(
    GZipMiddleware,
    minimum_size=1000,  # Only compress responses larger than 1KB
)

# Security
security = HTTPBearer()

# Authentication dependencies
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UserInfo:
    """Get current authenticated user from JWT token."""
    token = credentials.credentials
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_manager = get_user_manager()
    user = user_manager.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return UserInfo(**user)

async def get_current_admin_user(current_user: UserInfo = Depends(get_current_user)) -> UserInfo:
    """Get current user and verify admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user


def _safe_document_filename(filename: str) -> str:
    """Validate filename to prevent path traversal. Returns sanitized name or raises HTTPException."""
    safe = os.path.basename(filename).strip()
    if not safe or safe.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if ".." in safe or "/" in safe or "\\" in safe:
        raise HTTPException(status_code=400, detail="Invalid filename: path traversal not allowed")
    return safe


@app.on_event("startup")
def startup_event():
    logger.info("🚀 FastAPI app is starting...")
    
    # Initialize database if available
    if _use_db:
        try:
            init_db()
            if is_db_available():
                logger.info("📊 Using PostgreSQL database for user storage")
                # Initialize default admin user in database
                try:
                    if DBUserManager.initialize_default_admin():
                        logger.info("✅ Default admin user created in database (username: admin, password: REDACTED)")
                except Exception as e:
                    logger.warning(f"Could not initialize default admin in database: {e}")
            else:
                logger.warning("⚠️ Database not available, falling back to JSON file storage")
        except Exception as e:
            logger.warning(f"Database initialization failed: {e}, using JSON file storage")
    
    # Fallback: Initialize default admin user in JSON if database not available
    if not _use_db or not is_db_available():
        try:
            if UserManager.initialize_default_admin():
                logger.info("✅ Default admin user created in JSON storage (username: admin, password: REDACTED)")
        except Exception as e:
            logger.warning(f"Could not initialize default admin: {e}")

@app.get("/")
def root():
    return {"message": "📚 Knowledge Assistant API is running"}

# Authentication endpoints
@app.post("/auth/register", response_model=UserInfo)
async def register(user_data: UserRegister, request: FastAPIRequest = None):
    """Register a new user."""
    try:
        # Validate role
        if user_data.role not in ["user", "admin"]:
            raise HTTPException(status_code=400, detail="Invalid role. Must be 'user' or 'admin'")
        
        user_manager = get_user_manager()
        user = user_manager.create_user(
            username=user_data.username,
            email=user_data.email,
            password=user_data.password,
            role=user_data.role
        )
        logger.info(f"New user registered: {user_data.username}")
        
        # Log audit event
        ip_address = None
        if request:
            ip_address = (
                request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
                request.headers.get("X-Real-IP", "") or
                (request.client.host if request.client else None)
            )
        log_audit_event(
            event_type="user_created",
            user_id=user["id"],
            username=user_data.username,
            ip_address=ip_address,
            status="success",
            details={"role": user_data.role}
        )
        
        return UserInfo(**user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")

@app.post("/auth/login", response_model=Token)
async def login(credentials: UserLogin, request: FastAPIRequest = None):
    """Login and get access token."""
    user_manager = get_user_manager()
    result = user_manager.authenticate_user(credentials.username, credentials.password)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check for errors (account locked, invalid credentials)
    if isinstance(result, dict) and "error" in result:
        error_type = result.get("error")
        if error_type == "account_locked":
            unlock_time = result.get("unlock_time")
            # Log audit event
            ip_address = None
            if request:
                ip_address = (
                    request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
                    request.headers.get("X-Real-IP", "") or
                    (request.client.host if request.client else None)
                )
            log_audit_event(
                event_type="login_locked",
                username=credentials.username,
                ip_address=ip_address,
                status="failed",
                error_message="Account locked"
            )
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"Account is locked due to too many failed login attempts. Please try again after {unlock_time} or contact an administrator.",
            )
        elif error_type == "invalid_credentials":
            attempts_remaining = result.get("attempts_remaining", 0)
            # Log audit event
            ip_address = None
            if request:
                ip_address = (
                    request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
                    request.headers.get("X-Real-IP", "") or
                    (request.client.host if request.client else None)
                )
            log_audit_event(
                event_type="login_failed",
                username=credentials.username,
                ip_address=ip_address,
                status="failed",
                error_message="Invalid credentials",
                details={"attempts_remaining": attempts_remaining}
            )
            detail_msg = "Incorrect username or password"
            if attempts_remaining > 0:
                detail_msg += f". {attempts_remaining} attempt(s) remaining before account lockout."
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=detail_msg,
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    # Successful authentication
    user = result
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["id"], "username": user["username"], "role": user["role"]},
        expires_delta=access_token_expires
    )
    
    # Get lockout status for user info
    is_locked, unlock_time = UserManager.is_account_locked(user["id"])
    
    # Check if 2FA is enabled
    twofa_enabled = UserManager.is_2fa_enabled(user["id"])
    
    user_info = UserInfo(
        **user,
        locked=is_locked,
        unlock_time=unlock_time,
        failed_attempts=0,  # Reset on successful login
        twofa_enabled=twofa_enabled
    )
    
    # If 2FA is enabled, return a special response indicating 2FA is required
    if twofa_enabled:
        return {
            "access_token": None,  # No token yet, need 2FA
            "token_type": "bearer",
            "user": user_info,
            "requires_2fa": True
        }
    
    # Create refresh token
    refresh_token = create_refresh_token(user["id"])
    
    # Get client info for session
    ip_address = None
    user_agent = None
    if request:
        ip_address = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
            request.headers.get("X-Real-IP", "") or
            (request.client.host if request.client else None)
        )
        user_agent = request.headers.get("User-Agent", "")
    
    # Create session
    session_id = create_session(
        user_id=user["id"],
        access_token=access_token,
        refresh_token=refresh_token,
        ip_address=ip_address,
        user_agent=user_agent,
        device_info=None  # Could parse from user agent
    )
    
    logger.info(f"User logged in: {credentials.username} (session: {session_id[:8]}...)")
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user_info,
        "requires_2fa": False,
        "session_id": session_id
    }

@app.get("/auth/me", response_model=UserInfo)
async def get_current_user_info(current_user: UserInfo = Depends(get_current_user)):
    """Get current user information."""
    return current_user

@app.post("/auth/change-password")
async def change_password(
    password_data: ChangePasswordRequest,
    current_user: UserInfo = Depends(get_current_user)
):
    """Change user password."""
    success, error_message = UserManager.change_password(
        current_user.id,
        password_data.old_password,
        password_data.new_password
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message or "Failed to change password. Please check your current password."
        )
    logger.info(f"Password changed for user: {current_user.username}")
    return {"message": "Password changed successfully"}

@app.post("/auth/password-reset/request", response_model=PasswordResetResponse)
async def request_password_reset(request: PasswordResetRequest, http_request: FastAPIRequest = None):
    """Request a password reset token."""
    try:
        # Get client IP address
        client_ip = None
        if http_request:
            # Try to get IP from various headers (for proxies/load balancers)
            client_ip = (
                http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
                http_request.headers.get("X-Real-IP", "") or
                http_request.client.host if http_request.client else None
            )
        
        # Cleanup expired tokens first
        UserManager.cleanup_expired_tokens()
        
        token = UserManager.generate_reset_token(request.email, ip_address=client_ip)
        
        # For security, always return success message (don't reveal if email exists)
        if token:
            # Send email if configured
            email_sent = False
            if EmailService and EmailService.is_configured():
                email_sent = await EmailService.send_password_reset_email(request.email, token)
                if email_sent:
                    logger.info(f"Password reset email sent to {request.email}")
                else:
                    logger.warning(f"Failed to send password reset email to {request.email}")
            
            # In development mode (email not configured), return token
            if not EmailService or not EmailService.is_configured():
                logger.info(f"Password reset token generated for {request.email} (email not configured)")
                return {
                    "message": "If the email exists, a password reset link has been sent.",
                    "token": token  # Only returned when email service is not configured
                }
            else:
                return {
                    "message": "If the email exists, a password reset link has been sent."
                }
        else:
            # Still return success to prevent email enumeration
            return {
                "message": "If the email exists, a password reset link has been sent."
            }
    except Exception as e:
        logger.error(f"Error generating reset token: {e}")
        # Still return success to prevent information leakage
        return {
            "message": "If the email exists, a password reset link has been sent."
        }

@app.post("/auth/password-reset/verify")
async def verify_reset_token(request: PasswordResetVerifyRequest):
    """Verify a password reset token."""
    token_info = UserManager.verify_reset_token(request.token)
    if not token_info:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired reset token"
        )
    return {
        "message": "Token is valid",
        "email": token_info.get("email")
    }

@app.post("/auth/password-reset/confirm")
async def confirm_password_reset(
    request: PasswordResetConfirmRequest,
    http_request: FastAPIRequest = None
):
    """Reset password using a reset token."""
    success, error_message = UserManager.reset_password_with_token(
        request.token,
        request.new_password
    )
    
    if not success:
        # Log audit event
        ip_address = None
        if http_request:
            ip_address = (
                http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
                http_request.headers.get("X-Real-IP", "") or
                (http_request.client.host if http_request.client else None)
            )
        log_audit_event(
            event_type="password_reset",
            ip_address=ip_address,
            status="failed",
            error_message=error_message
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message or "Invalid or expired reset token, or password reset failed."
        )
    
    # Get user info for audit log
    token_info = UserManager.verify_reset_token(request.token)
    user_id = token_info.get("user_id") if token_info else None
    username = None
    if user_id:
        user_manager = get_user_manager()
        user = user_manager.get_user_by_id(user_id)
        username = user.get("username") if user else None
    
    # Log audit event
    ip_address = None
    if http_request:
        ip_address = (
            http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
            http_request.headers.get("X-Real-IP", "") or
            (http_request.client.host if http_request.client else None)
        )
    log_audit_event(
        event_type="password_reset",
        user_id=user_id,
        username=username,
        ip_address=ip_address,
        status="success"
    )
    
    logger.info("Password reset successful via token")
    return {"message": "Password has been reset successfully. You can now login with your new password."}

# User management endpoints (admin only)
@app.get("/auth/users", response_model=UserListResponse)
async def list_users(current_user: UserInfo = Depends(get_current_admin_user)):
    """List all users (admin only)."""
    user_manager = get_user_manager()
    users = user_manager.list_users()
    return {"users": [UserInfo(**user) for user in users], "total": len(users)}

@app.put("/auth/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    role_data: UpdateUserRoleRequest,
    current_user: UserInfo = Depends(get_current_admin_user),
    http_request: FastAPIRequest = None
):
    """Update user role (admin only)."""
    if role_data.role not in ["user", "admin"]:
        raise HTTPException(status_code=400, detail="Invalid role")
    
    # Get target user info
    target_user = UserManager.get_user_by_id(user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    old_role = target_user.get("role")
    user_manager = get_user_manager()
    success = user_manager.update_user_role(user_id, role_data.role)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Log audit event
    ip_address = None
    if http_request:
        ip_address = (
            http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
            http_request.headers.get("X-Real-IP", "") or
            (http_request.client.host if http_request.client else None)
        )
    log_audit_event(
        event_type="role_changed",
        user_id=user_id,
        username=target_user.get("username"),
        ip_address=ip_address,
        status="success",
        details={
            "changed_by": current_user.username,
            "old_role": old_role,
            "new_role": role_data.role
        }
    )
    
    return {"message": "User role updated successfully"}

@app.post("/auth/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: str,
    current_user: UserInfo = Depends(get_current_admin_user),
    http_request: FastAPIRequest = None
):
    """Deactivate a user (admin only)."""
    target_user = UserManager.get_user_by_id(user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_manager = get_user_manager()
    success = user_manager.deactivate_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Log audit event
    ip_address = None
    if http_request:
        ip_address = (
            http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
            http_request.headers.get("X-Real-IP", "") or
            (http_request.client.host if http_request.client else None)
        )
    log_audit_event(
        event_type="user_deactivated",
        user_id=user_id,
        username=target_user.get("username"),
        ip_address=ip_address,
        status="success",
        details={"deactivated_by": current_user.username}
    )
    
    return {"message": "User deactivated successfully"}

@app.post("/auth/users/{user_id}/activate")
async def activate_user(
    user_id: str,
    current_user: UserInfo = Depends(get_current_admin_user),
    http_request: FastAPIRequest = None
):
    """Activate a user (admin only)."""
    target_user = UserManager.get_user_by_id(user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_manager = get_user_manager()
    success = user_manager.activate_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Log audit event
    ip_address = None
    if http_request:
        ip_address = (
            http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
            http_request.headers.get("X-Real-IP", "") or
            (http_request.client.host if http_request.client else None)
        )
    log_audit_event(
        event_type="user_activated",
        user_id=user_id,
        username=target_user.get("username"),
        ip_address=ip_address,
        status="success",
        details={"activated_by": current_user.username}
    )
    
    return {"message": "User activated successfully"}

@app.post("/auth/users/{user_id}/unlock")
async def unlock_user_account(
    user_id: str,
    current_user: UserInfo = Depends(get_current_admin_user),
    http_request: FastAPIRequest = None
):
    """Unlock a locked user account (admin only)."""
    target_user = UserManager.get_user_by_id(user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found or not locked")
    
    user_manager = get_user_manager()
    success = user_manager.unlock_account(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found or not locked")
    
    # Log audit event
    ip_address = None
    if http_request:
        ip_address = (
            http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
            http_request.headers.get("X-Real-IP", "") or
            (http_request.client.host if http_request.client else None)
        )
    log_audit_event(
        event_type="account_unlocked",
        user_id=user_id,
        username=target_user.get("username"),
        ip_address=ip_address,
        status="success",
        details={"unlocked_by": current_user.username}
    )
    
    return {"message": "Account unlocked successfully"}

# 2FA endpoints
@app.post("/auth/2fa/setup", response_model=TwoFASetupResponse)
async def setup_2fa(current_user: UserInfo = Depends(get_current_user)):
    """Setup 2FA for the current user."""
    secret, qr_code_uri, backup_codes = UserManager.setup_2fa(
        current_user.id,
        current_user.username
    )
    return {
        "secret": secret,
        "qr_code_uri": qr_code_uri,
        "backup_codes": backup_codes
    }

@app.post("/auth/2fa/verify")
async def verify_and_enable_2fa(
    request: TwoFAVerifyRequest,
    current_user: UserInfo = Depends(get_current_user),
    http_request: FastAPIRequest = None
):
    """Verify 2FA code and enable 2FA."""
    success, error_message = UserManager.verify_and_enable_2fa(
        current_user.id,
        request.code
    )
    if not success:
        # Log audit event
        ip_address = None
        if http_request:
            ip_address = (
                http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
                http_request.headers.get("X-Real-IP", "") or
                (http_request.client.host if http_request.client else None)
            )
        log_audit_event(
            event_type="2fa_enabled",
            user_id=current_user.id,
            username=current_user.username,
            ip_address=ip_address,
            status="failed",
            error_message=error_message
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message or "Failed to verify 2FA code"
        )
    
    # Log audit event
    ip_address = None
    if http_request:
        ip_address = (
            http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
            http_request.headers.get("X-Real-IP", "") or
            (http_request.client.host if http_request.client else None)
        )
    log_audit_event(
        event_type="2fa_enabled",
        user_id=current_user.id,
        username=current_user.username,
        ip_address=ip_address,
        status="success"
    )
    
    # Get backup codes
    backup_codes = UserManager.get_backup_codes(current_user.id)
    
    return {
        "message": "2FA enabled successfully",
        "backup_codes": backup_codes
    }

@app.post("/auth/2fa/verify-login")
async def verify_2fa_login(
    request: TwoFALoginRequest,
    username: str,
    http_request: FastAPIRequest = None
):
    """
    Verify 2FA code during login.
    This endpoint is called after initial password authentication.
    """
    user_manager = get_user_manager()
    user = user_manager.get_user_by_username(username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Verify 2FA code
    if UserManager.verify_2fa_login(user["id"], request.code):
        # Generate access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user["id"], "username": user["username"], "role": user["role"]},
            expires_delta=access_token_expires
        )
        
        # Create refresh token
        refresh_token = create_refresh_token(user["id"])
        
        # Get client info for session
        ip_address = None
        user_agent = None
        if http_request:
            ip_address = (
                http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
                http_request.headers.get("X-Real-IP", "") or
                (http_request.client.host if http_request.client else None)
            )
            user_agent = http_request.headers.get("User-Agent", "")
        
        # Create session
        session_id = create_session(
            user_id=user["id"],
            access_token=access_token,
            refresh_token=refresh_token,
            ip_address=ip_address,
            user_agent=user_agent,
            device_info=None
        )
        
        # Get lockout status
        is_locked, unlock_time = UserManager.is_account_locked(user["id"])
        
        user_info = UserInfo(
            **user,
            locked=is_locked,
            unlock_time=unlock_time,
            failed_attempts=0,
            twofa_enabled=True
        )
        
        logger.info(f"2FA login successful for user: {username} (session: {session_id[:8]}...)")
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": user_info,
            "session_id": session_id
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid 2FA code"
        )

@app.post("/auth/2fa/disable")
async def disable_2fa(
    current_user: UserInfo = Depends(get_current_user),
    http_request: FastAPIRequest = None
):
    """Disable 2FA for the current user."""
    success = UserManager.disable_2fa(current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is not enabled for this user"
        )
    
    # Log audit event
    ip_address = None
    if http_request:
        ip_address = (
            http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
            http_request.headers.get("X-Real-IP", "") or
            (http_request.client.host if http_request.client else None)
        )
    log_audit_event(
        event_type="2fa_disabled",
        user_id=current_user.id,
        username=current_user.username,
        ip_address=ip_address,
        status="success"
    )
    
    return {"message": "2FA disabled successfully"}

@app.get("/auth/2fa/backup-codes")
async def get_backup_codes(current_user: UserInfo = Depends(get_current_user)):
    """Get unused backup codes for the current user."""
    codes = UserManager.get_backup_codes(current_user.id)
    if codes is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="2FA is not set up for this user"
        )
    return {"backup_codes": codes}

@app.post("/auth/2fa/regenerate-backup-codes")
async def regenerate_backup_codes(current_user: UserInfo = Depends(get_current_user)):
    """Regenerate backup codes for the current user."""
    codes = UserManager.regenerate_backup_codes(current_user.id)
    if not codes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is not set up for this user"
        )
    return {
        "message": "Backup codes regenerated successfully",
        "backup_codes": codes
    }

# Session management endpoints
@app.get("/auth/sessions", response_model=SessionListResponse)
async def get_sessions(
    current_user: UserInfo = Depends(get_current_user),
    http_request: FastAPIRequest = None
):
    """Get all active sessions for the current user."""
    sessions = get_user_sessions(current_user.id)
    
    # Mark current session
    current_token = None
    if http_request:
        auth_header = http_request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            current_token = auth_header.split(" ")[1]
    
    if current_token:
        current_session = get_session_by_token(current_token)
        if current_session:
            for session in sessions:
                if session["session_id"] == current_session.get("session_id"):
                    session["is_current"] = True
                    break
    
    return {
        "sessions": [SessionInfo(**s) for s in sessions],
        "total": len(sessions)
    }

@app.post("/auth/sessions/{session_id}/revoke")
async def revoke_user_session(
    session_id: str,
    current_user: UserInfo = Depends(get_current_user),
    http_request: FastAPIRequest = None
):
    """Revoke a specific session (user can only revoke their own sessions)."""
    # Verify session belongs to user
    sessions = get_user_sessions(current_user.id)
    session_ids = [s["session_id"] for s in sessions]
    
    if session_id not in session_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    success = revoke_session(session_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to revoke session"
        )
    
    # Log audit event
    ip_address = None
    if http_request:
        ip_address = (
            http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
            http_request.headers.get("X-Real-IP", "") or
            (http_request.client.host if http_request.client else None)
        )
    log_audit_event(
        event_type="session_revoked",
        user_id=current_user.id,
        username=current_user.username,
        ip_address=ip_address,
        status="success",
        details={"session_id": session_id[:8]}
    )
    
    logger.info(f"Session revoked by user: {current_user.username}")
    return {"message": "Session revoked successfully"}

@app.post("/auth/sessions/revoke-all")
async def revoke_all_sessions(
    current_user: UserInfo = Depends(get_current_user),
    http_request: FastAPIRequest = None
):
    """Revoke all sessions except the current one."""
    current_session_id = None
    
    if http_request:
        auth_header = http_request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            current_token = auth_header.split(" ")[1]
            current_session = get_session_by_token(current_token)
            if current_session:
                current_session_id = current_session.get("session_id")
    
    revoked_count = revoke_all_user_sessions(current_user.id, exclude_session_id=current_session_id)
    
    # Log audit event
    ip_address = None
    if http_request:
        ip_address = (
            http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
            http_request.headers.get("X-Real-IP", "") or
            (http_request.client.host if http_request.client else None)
        )
    log_audit_event(
        event_type="session_revoked",
        user_id=current_user.id,
        username=current_user.username,
        ip_address=ip_address,
        status="success",
        details={"revoked_count": revoked_count, "action": "revoke_all_other"}
    )
    
    logger.info(f"All sessions revoked by user: {current_user.username} (except current)")
    return {"message": "All other sessions revoked successfully"}

@app.post("/auth/refresh", response_model=TokenRefreshResponse)
async def refresh_token(request: RefreshTokenRequest):
    """Refresh access token using refresh token."""
    user_id = verify_refresh_token(request.refresh_token)
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )
    
    # Get user info
    user_manager = get_user_manager()
    user = user_manager.get_user_by_id(user_id)
    if not user or not user.get("active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    # Generate new tokens
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    new_access_token = create_access_token(
        data={"sub": user["id"], "username": user["username"], "role": user["role"]},
        expires_delta=access_token_expires
    )
    new_refresh_token = create_refresh_token(user["id"])
    
    # Update session with new tokens
    sessions_data = load_sessions()
    sessions = sessions_data.get("sessions", [])
    
    for session in sessions:
        if session.get("refresh_token") == request.refresh_token and session.get("active", False):
            session["access_token"] = new_access_token
            session["refresh_token"] = new_refresh_token
            session["last_activity"] = datetime.now().isoformat()
            save_sessions(sessions_data)
            break
    
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer"
    }

# Profile management endpoints
@app.get("/auth/profile", response_model=ProfileResponse)
async def get_profile(current_user: UserInfo = Depends(get_current_user)):
    """Get current user's profile with preferences."""
    profile = UserManager.get_user_profile(current_user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Convert to UserInfo
    user_info = UserInfo(
        id=profile.get("id"),
        username=profile.get("username"),
        email=profile.get("email"),
        role=profile.get("role"),
        created_at=profile.get("created_at"),
        last_login=profile.get("last_login"),
        active=profile.get("active", True),
        locked=profile.get("locked", False),
        unlock_time=profile.get("unlock_time"),
        failed_attempts=profile.get("failed_attempts", 0),
        password_expires_at=profile.get("password_expires_at"),
        password_expired=profile.get("password_expired", False),
        twofa_enabled=profile.get("twofa_enabled", False),
        display_name=profile.get("display_name"),
        bio=profile.get("bio"),
        avatar=profile.get("avatar")
    )
    
    prefs = profile.get("preferences", {})
    preferences = UserPreferences(
        theme=prefs.get("theme", "light"),
        notifications_enabled=prefs.get("notifications_enabled", True),
        email_notifications=prefs.get("email_notifications", True),
        language=prefs.get("language", "en"),
        default_settings=prefs.get("default_settings", {})
    )
    
    return ProfileResponse(user=user_info, preferences=preferences)

@app.put("/auth/profile", response_model=UserInfo)
async def update_profile(
    profile_data: ProfileUpdateRequest,
    current_user: UserInfo = Depends(get_current_user),
    http_request: FastAPIRequest = None
):
    """Update user profile."""
    success = UserManager.update_user_profile(
        current_user.id,
        display_name=profile_data.display_name,
        email=profile_data.email,
        bio=profile_data.bio
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Log audit event
    ip_address = None
    if http_request:
        ip_address = (
            http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
            http_request.headers.get("X-Real-IP", "") or
            (http_request.client.host if http_request.client else None)
        )
    log_audit_event(
        event_type="profile_updated",
        user_id=current_user.id,
        username=current_user.username,
        ip_address=ip_address,
        status="success",
        details={"updated_fields": {k: v for k, v in profile_data.dict().items() if v is not None}}
    )
    
    # Get updated profile
    updated_profile = UserManager.get_user_profile(current_user.id)
    if not updated_profile:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserInfo(
        id=updated_profile.get("id"),
        username=updated_profile.get("username"),
        email=updated_profile.get("email"),
        role=updated_profile.get("role"),
        created_at=updated_profile.get("created_at"),
        last_login=updated_profile.get("last_login"),
        active=updated_profile.get("active", True),
        locked=updated_profile.get("locked", False),
        unlock_time=updated_profile.get("unlock_time"),
        failed_attempts=updated_profile.get("failed_attempts", 0),
        password_expires_at=updated_profile.get("password_expires_at"),
        password_expired=updated_profile.get("password_expired", False),
        twofa_enabled=updated_profile.get("twofa_enabled", False),
        display_name=updated_profile.get("display_name"),
        bio=updated_profile.get("bio"),
        avatar=updated_profile.get("avatar")
    )

@app.get("/auth/preferences", response_model=UserPreferences)
async def get_preferences(current_user: UserInfo = Depends(get_current_user)):
    """Get user preferences."""
    prefs = UserManager.get_user_preferences(current_user.id)
    return UserPreferences(**prefs)

@app.put("/auth/preferences", response_model=UserPreferences)
async def update_preferences(
    prefs_data: PreferencesUpdateRequest,
    current_user: UserInfo = Depends(get_current_user)
):
    """Update user preferences."""
    update_dict = {k: v for k, v in prefs_data.dict().items() if v is not None}
    UserManager.update_user_preferences(current_user.id, update_dict)
    
    # Get updated preferences
    updated_prefs = UserManager.get_user_preferences(current_user.id)
    return UserPreferences(**updated_prefs)

@app.post("/auth/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: UserInfo = Depends(get_current_user),
    http_request: FastAPIRequest = None
):
    """Upload user avatar."""
    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # Validate file size (max 2MB)
    MAX_AVATAR_SIZE = 2 * 1024 * 1024  # 2MB
    content = await file.read()
    if len(content) > MAX_AVATAR_SIZE:
        raise HTTPException(status_code=400, detail="Avatar file size must be less than 2MB")
    
    # Generate filename - restrict to safe image extensions
    ext = (os.path.splitext(file.filename)[1] or ".jpg").lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        ext = ".jpg"
    avatar_filename = f"{current_user.id}{ext}"
    avatar_path = os.path.join(AVATARS_DIR, avatar_filename)
    
    # Save file
    try:
        with open(avatar_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"Error saving avatar: {e}")
        raise HTTPException(status_code=500, detail="Failed to save avatar")
    
    # Update user profile with avatar path
    avatar_url = f"/avatars/{avatar_filename}"
    UserManager.update_user_profile(current_user.id, avatar=avatar_url)
    
    # Log audit event
    ip_address = None
    if http_request:
        ip_address = (
            http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
            http_request.headers.get("X-Real-IP", "") or
            (http_request.client.host if http_request.client else None)
        )
    log_audit_event(
        event_type="avatar_uploaded",
        user_id=current_user.id,
        username=current_user.username,
        ip_address=ip_address,
        status="success"
    )
    
    return {"message": "Avatar uploaded successfully", "avatar_url": avatar_url}

@app.get("/status")
def get_status(current_user: UserInfo = Depends(get_current_user)):
    """Get status of the knowledge base."""
    try:
        proc = get_processor()
        collection_count = proc.collection.count()
        
        # Detect files still waiting in source_files (uploaded but not yet ingested)
        pending_files = []
        try:
            source_files_dir = os.path.join(PROJECT_ROOT, "source_files")
            if os.path.isdir(source_files_dir):
                pending_files = [
                    f for f in os.listdir(source_files_dir)
                    if os.path.isfile(os.path.join(source_files_dir, f))
                ]
        except Exception as e:
            logger.warning(f"Could not inspect pending source_files: {e}")
            pending_files = []
        
        # Get list of unique documents
        try:
            # Sample some chunks to get document names
            sample = proc.collection.get(limit=min(100, collection_count))
            sources = set()
            if sample and 'metadatas' in sample:
                for meta in sample['metadatas']:
                    if meta and 'source' in meta:
                        sources.add(meta['source'])
            documents = list(sources)
        except Exception as e:
            logger.warning(f"Could not get document list: {e}")
            documents = []
        
        return {
            "status": "running",
            "knowledge_base_chunks": collection_count,
            "documents": documents,
            "document_count": len(documents),
            "pending_files_count": len(pending_files),
            "pending_files": pending_files,
            "is_processing": len(pending_files) > 0,
            "message": f"Knowledge base contains {collection_count} chunks from {len(documents)} document(s)"
        }
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return {
            "status": "error",
            "error": str(e)
        }

@app.get("/documents", response_model=DocumentListResponse)
def list_documents(current_user: UserInfo = Depends(get_current_user)):
    """List all documents in the knowledge base with details."""
    try:
        proc = get_processor()
        documents = proc.list_documents()
        total_chunks = proc.collection.count()
        
        return {
            "documents": documents,
            "total_documents": len(documents),
            "total_chunks": total_chunks
        }
    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents/{filename}", response_model=DocumentInfo)
def get_document_info(
    filename: str,
    current_user: UserInfo = Depends(get_current_user),
):
    """Get detailed information about a specific document."""
    try:
        filename = _safe_document_filename(filename)
        proc = get_processor()
        doc_info = proc.get_document_info(filename)
        if not doc_info:
            raise HTTPException(status_code=404, detail=f"Document '{filename}' not found")
        return doc_info
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/documents/{filename}", response_model=DeleteDocumentResponse)
def delete_document(
    filename: str,
    current_user: UserInfo = Depends(get_current_user),
    http_request: FastAPIRequest = None
):
    """Delete a document and all its chunks from the knowledge base."""
    try:
        filename = _safe_document_filename(filename)
        from .dependencies import get_processor
        document_processor = get_processor()
        deleted_count, error = document_processor.delete_document(filename)
        
        if error:
            raise HTTPException(status_code=404, detail=error)
        
        logger.info(f"Deleted {deleted_count} chunks for document '{filename}'")
        
        # Invalidate cache entries related to this document
        assistant = get_assistant()
        if assistant.enable_query_caching and assistant.query_cache:
            cleared = assistant.query_cache.invalidate(filename)
            logger.info(f"🗑️ Cache invalidated (cleared {cleared} entries) due to document deletion: {filename}")
        
        # Log audit event
        ip_address = None
        if http_request:
            ip_address = (
                http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
                http_request.headers.get("X-Real-IP", "") or
                (http_request.client.host if http_request.client else None)
            )
        log_audit_event(
            event_type="document_deleted",
            user_id=current_user.id,
            username=current_user.username,
            ip_address=ip_address,
            status="success",
            details={"filename": filename, "deleted_chunks": deleted_count}
        )
        
        return {
            "message": f"Successfully deleted document '{filename}'",
            "deleted_chunks": deleted_count,
            "filename": filename
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/reindex", response_model=dict)
def reindex_documents(
    new_embedding_model: str = None,
    current_user: UserInfo = Depends(get_current_user),
    http_request: FastAPIRequest = None
):
    """Re-index all documents with a new embedding model.
    
    This is required when changing the embedding model because embeddings
    are model-specific. All existing documents will be re-processed.
    
    Args:
        new_embedding_model: Optional new embedding model name. 
                           If not provided, uses the model from processor config.
                           Options: "all-MiniLM-L6-v2", "all-mpnet-base-v2", 
                                   "BAAI/bge-large-en-v1.5"
    """
    try:
        # Use provided model or default to the one in processor
        if new_embedding_model:
            model_to_use = new_embedding_model
        else:
            proc = get_processor()
            model_to_use = proc.embedding_model if hasattr(proc, 'embedding_model') else "all-mpnet-base-v2"
        
        logger.info(f"Starting re-indexing with model: {model_to_use}")
        
        # Perform re-indexing
        proc = get_processor()
        success, message = proc.reindex_with_new_model(model_to_use)
        
        if not success:
            raise HTTPException(status_code=500, detail=message)
        
        # Log audit event
        ip_address = None
        if http_request:
            ip_address = (
                http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
                http_request.headers.get("X-Real-IP", "") or
                (http_request.client.host if http_request.client else None)
            )
        log_audit_event(
            event_type="documents_reindexed",
            user_id=current_user.id,
            username=current_user.username,
            ip_address=ip_address,
            status="success",
            details={"embedding_model": model_to_use, "message": message}
        )
        
        return {
            "message": message,
            "embedding_model": model_to_use,
            "success": True
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error re-indexing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Chunking Strategy Configuration Endpoints
@app.get("/chunking/config", response_model=ChunkingConfigResponse)
def get_chunking_config(current_user: UserInfo = Depends(get_current_user)):
    """Get current chunking configuration."""
    try:
        # Only admins can view/modify chunking config
        if current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Only admins can view chunking configuration")
        
        available_strategies = [
            "adaptive", "semantic", "recursive", "sliding_window", 
            "hierarchical", "paragraph", "sentence"
        ]
        
        proc = get_processor()
        return {
            "current_strategy": getattr(proc, 'chunking_strategy', 'adaptive'),
            "chunk_size": getattr(proc, 'chunk_size', 800),
            "overlap": getattr(proc, 'overlap', 150),
            "min_chunk_size": getattr(proc, 'min_chunk_size', 100),
            "available_strategies": available_strategies
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting chunking config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chunking/config", response_model=ChunkingConfigResponse)
def update_chunking_config(
    request: ChunkingConfigRequest,
    current_user: UserInfo = Depends(get_current_user),
    http_request: FastAPIRequest = None
):
    """Update chunking configuration."""
    try:
        # Only admins can modify chunking config
        if current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Only admins can modify chunking configuration")
        
        available_strategies = [
            "adaptive", "semantic", "recursive", "sliding_window", 
            "hierarchical", "paragraph", "sentence"
        ]
        
        if request.strategy not in available_strategies:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid strategy. Available: {', '.join(available_strategies)}"
            )
        
        # Update processor configuration
        proc = get_processor()
        proc.chunking_strategy = request.strategy
        if request.chunk_size is not None:
            proc.chunk_size = request.chunk_size
        if request.overlap is not None:
            proc.overlap = request.overlap
        if request.min_chunk_size is not None:
            proc.min_chunk_size = request.min_chunk_size
        
        # Log audit event
        ip_address = None
        if http_request:
            ip_address = (
                http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
                http_request.headers.get("X-Real-IP", "") or
                (http_request.client.host if http_request.client else None)
            )
        log_audit_event(
            event_type="chunking_config_updated",
            user_id=current_user.id,
            username=current_user.username,
            ip_address=ip_address,
            status="success",
            details={
                "strategy": request.strategy,
                "chunk_size": proc.chunk_size,
                "overlap": proc.overlap,
                "min_chunk_size": proc.min_chunk_size
            }
        )
        
        return {
            "current_strategy": proc.chunking_strategy,
            "chunk_size": proc.chunk_size,
            "overlap": proc.overlap,
            "min_chunk_size": proc.min_chunk_size,
            "available_strategies": available_strategies
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating chunking config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Search History Endpoints
@app.get("/history", response_model=HistoryResponse)
def get_history(limit: int = 50):
    """Get search history."""
    try:
        history = SearchHistory.get_history(limit=limit)
        return {
            "history": [HistoryEntry(**entry) for entry in history],
            "total": len(history)
        }
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/history")
def clear_history():
    """Clear all search history."""
    try:
        SearchHistory.clear_history()
        return {"message": "History cleared successfully"}
    except Exception as e:
        logger.error(f"Error clearing history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/history/{timestamp}")
def delete_history_item(timestamp: str):
    """Delete a specific history item."""
    try:
        SearchHistory.delete_history_item(timestamp)
        return {"message": "History item deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting history item: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Saved Queries Endpoints
@app.get("/saved-queries", response_model=SavedQueriesResponse)
def get_saved_queries():
    """Get all saved queries."""
    try:
        saved = SavedQueries.get_all()
        return {
            "saved_queries": [SavedQuery(**item) for item in saved],
            "total": len(saved)
        }
    except Exception as e:
        logger.error(f"Error getting saved queries: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/saved-queries", response_model=SavedQuery)
def save_query(payload: SaveQueryRequest):
    """Save a query."""
    try:
        entry = SavedQueries.save_query(
            query=payload.query,
            name=payload.name,
            description=payload.description
        )
        return SavedQuery(**entry)
    except Exception as e:
        logger.error(f"Error saving query: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/saved-queries", response_model=SavedQuery)
def update_saved_query(payload: UpdateSavedQueryRequest):
    """Update a saved query."""
    try:
        entry = SavedQueries.update_saved_query(
            query=payload.query,
            name=payload.name,
            description=payload.description
        )
        if not entry:
            raise HTTPException(status_code=404, detail="Saved query not found")
        return SavedQuery(**entry)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating saved query: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/saved-queries/{query:path}")
def delete_saved_query(query: str):
    """Delete a saved query."""
    try:
        SavedQueries.delete_saved_query(query)
        return {"message": "Saved query deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting saved query: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/saved-queries/{query:path}/use")
def use_saved_query(query: str):
    """Increment usage count for a saved query."""
    try:
        SavedQueries.increment_usage(query)
        return {"message": "Usage count updated"}
    except Exception as e:
        logger.error(f"Error updating usage: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Query Suggestions Endpoint
@app.get("/suggestions", response_model=SuggestionsResponse)
def get_suggestions(q: str = "", limit: int = 10, include_documents: bool = True):
    """Get query suggestions based on partial input, history, saved queries, and document content."""
    try:
        # Ensure assistant is set for document-based suggestions
        QuerySuggestions.set_assistant(get_assistant())
        
        suggestions_data = QuerySuggestions.get_suggestions(q, limit=limit, include_documents=include_documents)
        suggestions = [QuerySuggestion(**s) for s in suggestions_data]
        return {
            "suggestions": suggestions,
            "total": len(suggestions)
        }
    except Exception as e:
        logger.error(f"Error getting suggestions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Feedback Endpoints
@app.post("/feedback", response_model=FeedbackResponse)
def submit_feedback(payload: FeedbackRequest):
    """Submit feedback for an answer."""
    try:
        # Validate payload
        if not payload.query or not payload.response:
            raise HTTPException(status_code=400, detail="Query and response are required")
        
        # Store feedback first (this is the critical operation)
        entry = AnswerFeedback.add_feedback(
            query=payload.query,
            response=payload.response,
            rating=payload.rating,
            feedback_type=payload.feedback_type,
            comment=payload.comment,
            sources_count=payload.sources_count
        )
        logger.info(f"Feedback submitted: rating={payload.rating}, type={payload.feedback_type}")
        
        # Trigger learning from feedback (non-blocking, won't affect feedback submission)
        try:
            # Check if assistant has learning capability
            if hasattr(assistant, 'learn_from_feedback'):
                # Create a sources list from sources_count (we don't have full source info here)
                sources = [{"source": "Unknown", "relevance": 0.5}] * payload.sources_count if payload.sources_count > 0 else []
                
                get_assistant().learn_from_feedback(
                    query=payload.query,
                    answer=payload.response,
                    rating=payload.rating,
                    sources=sources,
                    comment=payload.comment,
                    feedback_type=payload.feedback_type
                )
            else:
                logger.debug("Learning from feedback not available (assistant doesn't have learn_from_feedback method)")
        except Exception as learn_error:
            # Don't fail the feedback submission if learning fails
            logger.warning(f"Learning from feedback failed (non-critical): {learn_error}")
            import traceback
            logger.debug(traceback.format_exc())
        
        return {
            "message": "Feedback submitted successfully",
            "feedback_id": entry.get("timestamp", "")
        }
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error submitting feedback: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error submitting feedback: {str(e)}")

@app.get("/feedback/stats", response_model=FeedbackStatsResponse)
def get_feedback_stats():
    """Get feedback statistics."""
    try:
        stats = AnswerFeedback.get_feedback_stats()
        return {
            "stats": FeedbackStats(**stats)
        }
    except Exception as e:
        logger.error(f"Error getting feedback stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/feedback", response_model=List[FeedbackEntry])
def get_feedback(limit: int = 50):
    """Get recent feedback entries."""
    try:
        feedback = AnswerFeedback.get_feedback(limit=limit)
        return [FeedbackEntry(**entry) for entry in feedback]
    except Exception as e:
        logger.error(f"Error getting feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": "Invalid input. Please check your request format."},
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later."},
    )

# Conversation Endpoints
@app.get("/conversations", response_model=ConversationListResponse)
def list_conversations():
    """List all conversations."""
    try:
        conversations = ConversationManager.get_all_conversations()
        return {
            "conversations": conversations,
            "total": len(conversations)
        }
    except Exception as e:
        logger.error(f"Error listing conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/conversations", response_model=Conversation)
def create_conversation(payload: CreateConversationRequest = None):
    """Create a new conversation."""
    try:
        title = payload.title if payload else None
        conversation = ConversationManager.create_conversation(title)
        return conversation
    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/conversations/{conversation_id}", response_model=Conversation)
def get_conversation(conversation_id: str):
    """Get a specific conversation by ID."""
    try:
        conversation = ConversationManager.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/conversations/{conversation_id}", response_model=Conversation)
def update_conversation(conversation_id: str, payload: UpdateConversationRequest):
    """Update a conversation's metadata."""
    try:
        conversation = ConversationManager.update_conversation(
            conversation_id,
            title=payload.title,
            context_enabled=payload.context_enabled
        )
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    """Delete a conversation."""
    try:
        ConversationManager.delete_conversation(conversation_id)
        return {"message": "Conversation deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/conversations/{conversation_id}/clear")
def clear_conversation(conversation_id: str):
    """Clear all messages from a conversation."""
    try:
        conversation = ConversationManager.clear_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"message": "Conversation cleared successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/conversations/{conversation_id}/messages")
def add_conversation_message(conversation_id: str, role: str, content: str, sources: List[dict] = None):
    """Add a message to a conversation."""
    try:
        message = ConversationManager.add_message(conversation_id, role, content, sources)
        if not message:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return message
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ask")
async def ask_question(payload: QuestionRequest):
    """Async endpoint for faster response handling with source citations."""
    try:
        logger.info(f"Query: {payload.query[:100]}...")  # Log truncated query
        
        import time
        start_time = time.time()
        
        # Get conversation context if conversation_id is provided
        conversation_context = []
        if payload.conversation_id:
            conversation_context = ConversationManager.get_conversation_context(
                payload.conversation_id,
                max_messages=5
            )
        
        # Process query asynchronously
        import asyncio
        loop = asyncio.get_event_loop()
        assistant = get_assistant()
        result = await loop.run_in_executor(
            None, 
            assistant.ask_question, 
            payload.query,
            payload.document_filters,
            conversation_context,
            None,  # advanced_filters - will be None for regular requests
            payload.language  # Pass user's language preference
        )
        
        # Unpack result (answer, sources, intent_info, confidence_info, verification_info)
        if len(result) == 5:
            answer, sources, intent_info, confidence_info, verification_info = result
        elif len(result) == 4:
            answer, sources, intent_info, confidence_info = result
            verification_info = None
        elif len(result) == 3:
            answer, sources, intent_info = result
            confidence_info = None
            verification_info = None
        else:
            # Backward compatibility: if only 2 values returned
            answer, sources = result
            intent_info = {"intent": "factual", "confidence": 0.5}
            confidence_info = None
            verification_info = None
        
        elapsed_time = time.time() - start_time
        confidence_log = f", confidence: {confidence_info.get('confidence', 'N/A')}" if confidence_info else ""
        logger.info(f"Response generated ({len(answer)} chars) with {len(sources)} sources, intent: {intent_info.get('intent', 'unknown')}{confidence_log} in {elapsed_time:.2f}s")
        
        # Record performance metric
        try:
            HealthMonitor.record_query(
                payload.query,
                elapsed_time,
                len(sources),
                success=True
            )
        except Exception as e:
            logger.warning(f"Failed to record query metric: {e}")
        
        # Record detailed analytics
        try:
            user_id = None
            if hasattr(payload, 'user_id'):
                user_id = payload.user_id
            elif hasattr(request, 'state') and hasattr(request.state, 'user'):
                user_id = request.state.user.id if hasattr(request.state.user, 'id') else None
            
            AnalyticsTracker.record_query_analytics(
                query=payload.query,
                response_time=elapsed_time,
                sources=sources,
                intent=intent_info.get("intent") if intent_info else None,
                confidence=confidence_info.get("confidence") if confidence_info else None,
                verification_status=verification_info.get("status") if verification_info else None,
                cache_hit=False,  # Will be updated if we track cache hits
                user_id=user_id
            )
        except Exception as e:
            logger.warning(f"Failed to record analytics: {e}")
        
        # Save to conversation if conversation_id is provided
        if payload.conversation_id:
            try:
                ConversationManager.add_message(
                    payload.conversation_id,
                    "user",
                    payload.query
                )
                ConversationManager.add_message(
                    payload.conversation_id,
                    "assistant",
                    answer,
                    sources
                )
            except Exception as e:
                logger.warning(f"Failed to save to conversation: {e}")
        
        # Save to search history
        try:
            SearchHistory.add_query(
                query=payload.query,
                response_length=len(answer),
                sources_count=len(sources)
            )
        except Exception as e:
            logger.warning(f"Failed to save to history: {e}")
        
        # Build response (omit intent to avoid QueryIntent NameError; pass None)
        intent_obj = None
        
        # Build confidence object
        confidence_obj = None
        if confidence_info:
            confidence_obj = ConfidenceScore(
                confidence=confidence_info.get("confidence", 0.5),
                level=confidence_info.get("level", "unknown"),
                factors=confidence_info.get("factors")
            )
        
        # Build verification object
        verification_obj = None
        if verification_info:
            verification_obj = AnswerVerification(
                status=verification_info.get("status", "not_verified"),
                supported=verification_info.get("supported", True),
                details=verification_info.get("details", ""),
                has_hallucinations=verification_info.get("has_hallucinations", False)
            )
        
        return {"response": answer, "sources": sources, "intent": intent_obj, "confidence": confidence_obj, "verification": verification_obj}
    except Exception as e:
        logger.error(f"Error: {type(e).__name__}: {e}")
        # Record error metric
        try:
            HealthMonitor.record_error(
                type(e).__name__,
                str(e),
                {"endpoint": "/ask", "query": payload.query[:100] if hasattr(payload, 'query') else ""}
            )
        except:
            pass
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ask/stream")
async def ask_question_stream(payload: QuestionRequest):
    """Streaming endpoint for real-time response with source citations."""
    async def generate():
        try:
            logger.info(f"Streaming query: {payload.query[:100]}...")
            import time
            import threading
            start_time = time.time()
            loop = asyncio.get_running_loop()

            def _elapsed() -> float:
                return time.time() - start_time

            def _sse(obj: dict) -> str:
                # ensure_ascii=False so non-English text survives streaming intact
                return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

            # Emit immediately so clients don't hit read-timeouts while we retrieve context / warm models
            yield _sse({"type": "status", "stage": "starting", "elapsed": round(_elapsed(), 1)})
            
            # Get conversation context if conversation_id is provided
            conversation_context = []
            is_followup = False
            if payload.conversation_id:
                conversation_context = ConversationManager.get_conversation_context(
                    payload.conversation_id,
                    max_messages=5
                )
                is_followup = len(conversation_context) > 0
            
            # Multi-language support: detect and translate query if needed
            assistant = get_assistant()
            query_for_retrieval = payload.query
            detected_language = assistant.default_language
            if assistant.enable_multilanguage:
                yield _sse({"type": "status", "stage": "detecting_language", "elapsed": round(_elapsed(), 1)})
                if payload.language:
                    detected_language = payload.language if payload.language in assistant.supported_languages else assistant.default_language
                else:
                    detected_language = await loop.run_in_executor(None, assistant.detect_language, payload.query)
                
                # Translate query to English for processing
                if detected_language != assistant.default_language:
                    yield _sse({"type": "status", "stage": "translating_query", "elapsed": round(_elapsed(), 1)})
                    # translate_text signature: translate_text(text, target_lang, source_lang)
                    # target is default_language (en), source is detected_language
                    translate_q_future = loop.run_in_executor(
                        None, assistant.translate_text, payload.query, assistant.default_language, detected_language
                    )
                    while True:
                        try:
                            # Shield so heartbeat timeouts don't cancel the underlying executor work
                            query_for_retrieval = await asyncio.wait_for(asyncio.shield(translate_q_future), timeout=2.0)
                            break
                        except asyncio.TimeoutError:
                            yield _sse({"type": "status", "stage": "translating_query", "elapsed": round(_elapsed(), 1)})
            
            # Enhance query for follow-up questions
            enhanced_query = query_for_retrieval
            if is_followup:
                # Extract key information from previous conversation
                previous_summary = []
                for msg in conversation_context[-4:]:  # Last 4 messages
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if role == "user":
                        previous_summary.append(f"User: {content[:80]}")
                    elif role == "assistant":
                        previous_summary.append(f"Assistant: {content[:120]}")
                
                if previous_summary:
                    context_hint = " | ".join(previous_summary)
                    enhanced_query = f"{query_for_retrieval} [Context: {context_hint}]"
            
            # Retrieve context (may be slow on first request while embedding model loads)
            yield _sse({"type": "status", "stage": "retrieving_context", "elapsed": round(_elapsed(), 1)})
            retrieve_future = loop.run_in_executor(
                None,
                assistant.retrieve_context,
                enhanced_query if is_followup else query_for_retrieval,
                8,  # k value (higher recall for summaries)
                payload.document_filters,
            )
            while True:
                try:
                    # Shield so heartbeat timeouts don't cancel the underlying executor work
                    context, sources = await asyncio.wait_for(asyncio.shield(retrieve_future), timeout=2.0)
                    break
                except asyncio.TimeoutError:
                    yield _sse({"type": "status", "stage": "retrieving_context", "elapsed": round(_elapsed(), 1)})
            
            if not context:
                context = ""
            
            # Send sources first
            yield _sse({"type": "sources", "sources": sources})
            
            # Add conversation context to assistant if provided
            if conversation_context:
                # Limit to last 6 messages to avoid token bloat
                recent_context = conversation_context[-6:] if len(conversation_context) > 6 else conversation_context
                for msg in recent_context:
                    if msg.get("role") in ["user", "assistant"]:
                        assistant.chat_history.append({
                            "role": msg.get("role"),
                            "content": msg.get("content", "")
                        })
            
            # Stream the response with follow-up awareness.
            # Important: assistant.generate_response_stream() is synchronous and can block;
            # run it in a background thread and forward chunks via an asyncio.Queue so we can send heartbeats.
            query_for_response = (
                query_for_retrieval
                if assistant.enable_multilanguage and detected_language != assistant.default_language
                else payload.query
            )
            yield _sse({"type": "status", "stage": "generating_answer", "elapsed": round(_elapsed(), 1)})

            q: asyncio.Queue = asyncio.Queue()

            def _producer():
                try:
                    for chunk in assistant.generate_response_stream(query_for_response, context, is_followup=is_followup):
                        loop.call_soon_threadsafe(q.put_nowait, {"type": "chunk", "content": chunk})
                except Exception as e:
                    loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": f"❌ Error: {str(e)}"})
                finally:
                    loop.call_soon_threadsafe(q.put_nowait, {"type": "producer_done"})

            threading.Thread(target=_producer, daemon=True).start()

            response_text = ""
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    yield _sse({"type": "status", "stage": "generating_answer", "elapsed": round(_elapsed(), 1)})
                    continue

                if item.get("type") == "producer_done":
                    break
                if item.get("type") == "error":
                    yield _sse({"type": "error", "content": item.get("content", "❌ Error")})
                    return
                if item.get("type") == "chunk":
                    chunk = item.get("content", "")
                    response_text += chunk
                    yield _sse({"type": "chunk", "content": chunk})
            
            # Calculate confidence score for streaming response
            confidence_info = None
            if assistant.enable_confidence_scoring:
                yield _sse({"type": "status", "stage": "scoring_confidence", "elapsed": round(_elapsed(), 1)})
                confidence_future = loop.run_in_executor(
                    None,
                    assistant.score_answer_confidence,
                    payload.query,
                    response_text.strip(),
                    context,
                    sources,
                )
                while True:
                    try:
                        # Shield so heartbeat timeouts don't cancel the underlying executor work
                        confidence_info = await asyncio.wait_for(asyncio.shield(confidence_future), timeout=2.0)
                        break
                    except asyncio.TimeoutError:
                        yield _sse({"type": "status", "stage": "scoring_confidence", "elapsed": round(_elapsed(), 1)})
            
            # Verify answer for streaming response
            verification_info = None
            if assistant.enable_answer_verification:
                yield _sse({"type": "status", "stage": "verifying_answer", "elapsed": round(_elapsed(), 1)})
                verify_future = loop.run_in_executor(
                    None,
                    assistant.verify_answer,
                    query_for_response,
                    response_text.strip(),
                    context,
                    sources,
                )
                while True:
                    try:
                        # Shield so heartbeat timeouts don't cancel the underlying executor work
                        verification_info = await asyncio.wait_for(asyncio.shield(verify_future), timeout=2.0)
                        break
                    except asyncio.TimeoutError:
                        yield _sse({"type": "status", "stage": "verifying_answer", "elapsed": round(_elapsed(), 1)})
            
            # Translate answer back to user's language if needed
            final_response = response_text.strip()
            if assistant.enable_multilanguage and detected_language != assistant.default_language:
                yield _sse({"type": "status", "stage": "translating_answer", "elapsed": round(_elapsed(), 1)})
                # translate_text signature: translate_text(text, target_lang, source_lang)
                # Use final_response (not response_text) so echo replacement is preserved when translating
                translate_a_future = loop.run_in_executor(
                    None, assistant.translate_text, final_response, detected_language, assistant.default_language
                )
                while True:
                    try:
                        # Shield so heartbeat timeouts don't cancel the underlying executor work
                        final_response = await asyncio.wait_for(asyncio.shield(translate_a_future), timeout=2.0)
                        break
                    except asyncio.TimeoutError:
                        yield _sse({"type": "status", "stage": "translating_answer", "elapsed": round(_elapsed(), 1)})
            
            # Send completion signal with confidence and verification
            yield _sse(
                {
                    "type": "done",
                    "full_response": final_response,
                    "confidence": confidence_info,
                    "verification": verification_info,
                }
            )
            
            # Record query metric
            try:
                response_time = time.time() - start_time
                HealthMonitor.record_query(payload.query, response_time, len(sources), success=True)
            except Exception as e:
                logger.warning(f"Failed to record query metric: {e}")
            
            # Record detailed analytics
            try:
                AnalyticsTracker.record_query_analytics(
                    query=payload.query,
                    response_time=response_time,
                    sources=sources,
                    intent=None,  # Could extract from response if available
                    confidence=confidence_info.get("confidence") if confidence_info else None,
                    verification_status=verification_info.get("status") if verification_info else None,
                    cache_hit=False,
                    user_id=None
                )
            except Exception as e:
                logger.warning(f"Failed to record analytics: {e}")
            
            # Save to conversation if conversation_id is provided
            if payload.conversation_id:
                try:
                    ConversationManager.add_message(
                        payload.conversation_id,
                        "user",
                        payload.query
                    )
                    ConversationManager.add_message(
                        payload.conversation_id,
                        "assistant",
                        response_text.strip(),
                        sources
                    )
                except Exception as e:
                    logger.warning(f"Failed to save to conversation: {e}")
            
            # Save to search history
            try:
                SearchHistory.add_query(
                    query=payload.query,
                    response_length=len(response_text),
                    sources_count=len(sources)
                )
            except Exception as e:
                logger.warning(f"Failed to save to history: {e}")
                
        except Exception as e:
            logger.error(f"Error in streaming: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': f'❌ Error: {str(e)}'}, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    current_user: UserInfo = Depends(get_current_user),
    http_request: FastAPIRequest = None
):
    # Maximum file size: 50MB
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB in bytes
    
    allowed_extensions = {".pdf", ".docx", ".txt", ".html", ".csv"}
    
    # Validate filename
    if not file.filename:
        logger.warning("File upload rejected: missing filename")
        raise HTTPException(status_code=400, detail="Filename is required")
    
    ext = os.path.splitext(file.filename)[1].lower()
    
    if ext not in allowed_extensions:
        logger.warning(f"Rejected file upload: {file.filename} (unsupported extension: {ext})")
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file type: {ext}. Supported types: {', '.join(allowed_extensions)}"
        )
    
    # Validate and sanitize filename
    filename = os.path.basename(file.filename)  # Remove any path components
    if not filename or filename.startswith('.'):
        logger.warning(f"Rejected file upload: invalid filename '{file.filename}'")
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    source_files_dir = os.path.join(PROJECT_ROOT, "source_files")
    
    try:
        # Create directory if it doesn't exist
        os.makedirs(source_files_dir, exist_ok=True)
    except OSError as e:
        logger.error(f"Failed to create source_files directory: {e}")
        raise HTTPException(
            status_code=500, 
            detail="Server configuration error: cannot create upload directory"
        )
    
    source_path = os.path.join(source_files_dir, filename)
    
    try:
        # Read file content with size validation
        content = await file.read()
        file_size = len(content)
        
        if file_size == 0:
            logger.warning(f"Rejected empty file: {filename}")
            raise HTTPException(status_code=400, detail="File is empty")
        
        if file_size > MAX_FILE_SIZE:
            logger.warning(f"Rejected file {filename}: size {file_size} exceeds limit {MAX_FILE_SIZE}")
            raise HTTPException(
                status_code=400, 
                detail=f"File size ({file_size / (1024*1024):.2f}MB) exceeds maximum allowed size (50MB)"
            )
        
        # Write file with proper error handling
        try:
            with open(source_path, "wb") as f:
                f.write(content)
            logger.info(f"📥 File saved to source_files: {source_path} (size: {file_size} bytes)")
        except PermissionError:
            logger.error(f"Permission denied writing to {source_path}")
            raise HTTPException(
                status_code=500,
                detail="Server error: permission denied when saving file"
            )
        except OSError as e:
            logger.error(f"OS error saving file {filename}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Server error: failed to save file - {str(e)}"
            )
        
        # Schedule background task
        background_tasks.add_task(process_and_move_file, source_path, ext)
        
        # Invalidate cache when new document is uploaded (will be processed in background)
        # Note: We invalidate by filename pattern, but since processing is async,
        # we'll invalidate all cache to be safe
        # Note: Only check cache if assistant has been initialized (lazy loading)
        try:
            assistant = get_assistant()
            if assistant.enable_query_caching and assistant.query_cache:
                cleared = assistant.query_cache.clear()
                logger.info(f"🗑️ Cache invalidated (cleared {cleared} entries) due to document upload: {filename}")
        except Exception:
            # Assistant not initialized yet, skip cache invalidation
            pass
        
        # Log audit event
        ip_address = None
        if http_request:
            ip_address = (
                http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
                http_request.headers.get("X-Real-IP", "") or
                (http_request.client.host if http_request.client else None)
            )
        log_audit_event(
            event_type="document_uploaded",
            user_id=current_user.id,
            username=current_user.username,
            ip_address=ip_address,
            status="success",
            details={"filename": file.filename, "content_type": file.content_type, "file_size": file_size}
        )
        
        return {"message": f"📤 {filename} is being processed in the background."}
    
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except MemoryError:
        logger.error(f"Memory error reading file {filename}")
        raise HTTPException(
            status_code=500,
            detail="Server error: insufficient memory to process file"
        )
    except Exception as e:
        logger.error(f"Unexpected error saving {filename}: {type(e).__name__}: {e}")
        # Clean up partial file if it exists
        if os.path.exists(source_path):
            try:
                os.remove(source_path)
            except:
                pass
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {str(e)}"
        )


def process_and_move_file(source_path: str, ext: str):
    filename = os.path.basename(source_path)
    
    # Validate source file exists
    if not os.path.exists(source_path):
        logger.error(f"❌ Source file not found: {source_path}")
        return
    
    if not os.path.isfile(source_path):
        logger.error(f"❌ Source path is not a file: {source_path}")
        return
    
    try:
        import time
        start_time = time.time()
        
        # Get processor instance (lazy loading)
        proc = get_processor()
        
        # Get initial chunk count
        initial_count = proc.collection.count()
        logger.info(f"📊 Knowledge base before processing: {initial_count} chunks")
        
        # Run the ingestion processor (this may move the file itself)
        proc.process_document(source_path)
        
        # Verify chunks were added
        final_count = proc.collection.count()
        chunks_added = final_count - initial_count
        
        # Calculate processing time
        processing_time = time.time() - start_time
        
        # Record document processing metric
        try:
            file_size = os.path.getsize(source_path) if os.path.exists(source_path) else 0
            HealthMonitor.record_document_processed(
                filename,
                chunks_added,
                file_size,
                success=(chunks_added > 0),
                processing_time=processing_time
            )
        except Exception as e:
            logger.warning(f"Failed to record document metric: {e}")
        
        if chunks_added > 0:
            logger.info(f"✅ Successfully added {chunks_added} chunks from {filename} (total: {final_count})")
        else:
            logger.warning(f"⚠️ No new chunks added from {filename} (may be duplicate or empty)")

        # Check if file still exists in source location (processor may have moved it)
        if not os.path.exists(source_path):
            logger.info(f"✅ {filename} processed and moved by processor")
            return

        # If file still exists, move it to ingested_files/<ext_without_dot>/
        ingested_dir = os.path.join(PROJECT_ROOT, "ingested_files", ext[1:])
        
        try:
            os.makedirs(ingested_dir, exist_ok=True)
        except OSError as e:
            logger.error(f"❌ Failed to create ingested directory {ingested_dir}: {e}")
            return
        
        ingested_path = os.path.join(ingested_dir, filename)

        # Check if destination file already exists
        if os.path.exists(ingested_path):
            # Remove the source file since it's already processed
            try:
                os.remove(source_path)
                logger.info(f"ℹ️ {filename} already exists in {ingested_dir}, removed duplicate from source")
            except PermissionError:
                logger.warning(f"⚠️ Permission denied removing duplicate source file {source_path}")
            except OSError as e:
                logger.warning(f"⚠️ OS error removing duplicate source file {source_path}: {e}")
            except Exception as remove_error:
                logger.warning(f"⚠️ Could not remove duplicate source file {source_path}: {remove_error}")
            return

        # Move the file using shutil.move (more robust than os.rename)
        try:
            shutil.move(source_path, ingested_path)
            logger.info(f"✅ {filename} processed and moved to {ingested_path}")
        except PermissionError:
            # File might be locked, log and leave it in source_files
            logger.warning(f"⚠️ Permission denied: Could not move {filename} - file may be in use")
        except OSError as e:
            if "No space left" in str(e) or "disk" in str(e).lower():
                logger.error(f"❌ Disk full: Cannot move {filename} - {e}")
            else:
                logger.error(f"❌ OS error moving {filename}: {e}")
        except shutil.Error as e:
            logger.error(f"❌ shutil error moving {filename}: {e}")
        except Exception as move_error:
            logger.error(f"❌ Unexpected error moving {filename}: {type(move_error).__name__}: {move_error}")

    except FileNotFoundError:
        logger.error(f"❌ File not found during processing: {source_path}")
    except PermissionError:
        logger.error(f"❌ Permission denied accessing file: {source_path}")
    except Exception as e:
        logger.error(f"❌ Background task failed for {filename}: {type(e).__name__}: {e}")


# Progress tracking for bulk operations (in-memory, simple implementation)
_bulk_operations_progress = {}
import threading
_progress_lock = threading.Lock()


@app.post("/upload/bulk", response_model=BulkUploadResponse)
async def bulk_upload_files(
    files: List[UploadFile] = File(..., description="Multiple files to upload"),
    background_tasks: BackgroundTasks = None,
    current_user: UserInfo = Depends(get_current_user),
    http_request: FastAPIRequest = None
):
    """Upload multiple files at once."""
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    allowed_extensions = {".pdf", ".docx", ".txt", ".html", ".csv"}
    source_files_dir = os.path.join(PROJECT_ROOT, "source_files")
    
    results = []
    successful = 0
    failed = 0
    
    # Create directory if it doesn't exist
    try:
        os.makedirs(source_files_dir, exist_ok=True)
    except OSError as e:
        logger.error(f"Failed to create source_files directory: {e}")
        raise HTTPException(status_code=500, detail="Server configuration error: cannot create upload directory")
    
    for file in files:
        filename = file.filename
        result = {"filename": filename, "status": "failed", "message": "", "chunks_added": 0}
        
        try:
            if not filename:
                result["message"] = "Filename is required"
                results.append(result)
                failed += 1
                continue
            
            ext = os.path.splitext(filename)[1].lower()
            if ext not in allowed_extensions:
                result["message"] = f"Unsupported file type: {ext}"
                results.append(result)
                failed += 1
                continue
            
            # Validate and sanitize filename
            filename = os.path.basename(filename)
            if not filename or filename.startswith('.'):
                result["message"] = "Invalid filename"
                results.append(result)
                failed += 1
                continue
            
            source_path = os.path.join(source_files_dir, filename)
            
            # Read file content
            content = await file.read()
            file_size = len(content)
            
            if file_size == 0:
                result["message"] = "File is empty"
                results.append(result)
                failed += 1
                continue
            
            if file_size > MAX_FILE_SIZE:
                result["message"] = f"File size ({file_size / (1024*1024):.2f}MB) exceeds maximum (50MB)"
                results.append(result)
                failed += 1
                continue
            
            # Write file
            try:
                with open(source_path, "wb") as f:
                    f.write(content)
                logger.info(f"📥 File saved to source_files: {source_path} (size: {file_size} bytes)")
            except Exception as e:
                result["message"] = f"Failed to save file: {str(e)}"
                results.append(result)
                failed += 1
                continue
            
            # Schedule background task
            background_tasks.add_task(process_and_move_file, source_path, ext)
            
            result["status"] = "success"
            result["message"] = f"File queued for processing"
            results.append(result)
            successful += 1
            
        except Exception as e:
            logger.error(f"Error processing file {filename}: {e}")
            result["message"] = f"Error: {str(e)}"
            results.append(result)
            failed += 1
    
    # Invalidate cache if any files were successfully uploaded
    # Note: Only check cache if assistant has been initialized (lazy loading)
    if successful > 0:
        try:
            assistant = get_assistant()
            if assistant.enable_query_caching and assistant.query_cache:
                cleared = assistant.query_cache.clear()
                logger.info(f"🗑️ Cache invalidated (cleared {cleared} entries) due to bulk document upload")
        except Exception:
            # Assistant not initialized yet, skip cache invalidation
            pass
    
    # Log audit event
    ip_address = None
    if http_request:
        ip_address = (
            http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
            http_request.headers.get("X-Real-IP", "") or
            (http_request.client.host if http_request.client else None)
        )
    log_audit_event(
        event_type="bulk_document_uploaded",
        user_id=current_user.id,
        username=current_user.username,
        ip_address=ip_address,
        status="success" if successful > 0 else "failed",
        details={"total_files": len(files), "successful": successful, "failed": failed}
    )
    
    return {
        "total_files": len(files),
        "successful": successful,
        "failed": failed,
        "results": results
    }


@app.post("/documents/batch-delete", response_model=BatchDeleteResponse)
def batch_delete_documents(
    request: BatchDeleteRequest,
    current_user: UserInfo = Depends(get_current_user),
    http_request: FastAPIRequest = None
):
    """Delete multiple documents at once."""
    if not request.filenames:
        raise HTTPException(status_code=400, detail="No filenames provided")
    
    results = []
    successful = 0
    failed = 0
    total_chunks_deleted = 0
    
    for filename in request.filenames:
        result = {"filename": filename, "status": "failed", "message": "", "chunks_deleted": 0}
        
        try:
            from .dependencies import get_processor
            doc_proc = get_processor()
            deleted_count, error = doc_proc.delete_document(filename)
            
            if error:
                result["message"] = error
                results.append(result)
                failed += 1
            else:
                result["status"] = "success"
                result["message"] = f"Successfully deleted"
                result["chunks_deleted"] = deleted_count
                results.append(result)
                successful += 1
                total_chunks_deleted += deleted_count
                logger.info(f"Deleted {deleted_count} chunks for document '{filename}'")
        except Exception as e:
            logger.error(f"Error deleting document {filename}: {e}")
            result["message"] = f"Error: {str(e)}"
            results.append(result)
            failed += 1
    
    # Invalidate cache if any documents were successfully deleted
    # Note: Only check cache if assistant has been initialized (lazy loading)
    if successful > 0:
        try:
            assistant = get_assistant()
            if assistant.enable_query_caching and assistant.query_cache:
                cleared = assistant.query_cache.clear()
                logger.info(f"🗑️ Cache invalidated (cleared {cleared} entries) due to batch document deletion")
        except Exception:
            # Assistant not initialized yet, skip cache invalidation
            pass
    
    # Log audit event
    ip_address = None
    if http_request:
        ip_address = (
            http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
            http_request.headers.get("X-Real-IP", "") or
            (http_request.client.host if http_request.client else None)
        )
    log_audit_event(
        event_type="batch_document_deleted",
        user_id=current_user.id,
        username=current_user.username,
        ip_address=ip_address,
        status="success" if successful > 0 else "failed",
        details={"total_files": len(request.filenames), "successful": successful, "failed": failed, "total_chunks_deleted": total_chunks_deleted}
    )
    
    return {
        "total_files": len(request.filenames),
        "successful": successful,
        "failed": failed,
        "total_chunks_deleted": total_chunks_deleted,
        "results": results
    }


def reprocess_document_in_background(filename: str, source_path: str, ext: str):
    """Reprocess a document in the background."""
    try:
        import time
        start_time = time.time()
        
        # Get processor instance
        proc = get_processor()
        
        # Get initial chunk count
        initial_count = proc.collection.count()
        
        # Delete existing chunks for this document first
        deleted_count, error = proc.delete_document(filename)
        if error and "not found" not in error.lower():
            logger.warning(f"Could not delete existing chunks for {filename}: {error}")
        
        # Process the document again
        proc = get_processor()
        proc.process_document(source_path)
        
        # Verify chunks were added
        final_count = proc.collection.count()
        chunks_added = final_count - initial_count
        
        processing_time = time.time() - start_time
        
        # Record document processing metric
        try:
            file_size = os.path.getsize(source_path) if os.path.exists(source_path) else 0
            HealthMonitor.record_document_processed(
                filename,
                chunks_added,
                file_size,
                success=(chunks_added > 0),
                processing_time=processing_time
            )
        except Exception as e:
            logger.warning(f"Failed to record document metric: {e}")
        
        if chunks_added > 0:
            logger.info(f"✅ Successfully reprocessed {filename}: {chunks_added} chunks added")
        else:
            logger.warning(f"⚠️ No new chunks added from {filename} after reprocessing")
            
    except Exception as e:
        logger.error(f"❌ Background reprocessing failed for {filename}: {type(e).__name__}: {e}")


@app.post("/documents/bulk-reprocess", response_model=BulkReprocessResponse)
def bulk_reprocess_documents(
    request: BulkReprocessRequest,
    background_tasks: BackgroundTasks = None,
    current_user: UserInfo = Depends(get_current_user),
    http_request: FastAPIRequest = None
):
    """Reprocess multiple documents (or all if no filenames provided)."""
    results = []
    successful = 0
    failed = 0
    
    # Get list of documents to reprocess
    if request.filenames:
        filenames_to_process = request.filenames
    else:
        # Reprocess all documents
        try:
            proc = get_processor()
            documents = proc.list_documents()
            filenames_to_process = [doc["filename"] for doc in documents]
        except Exception as e:
            logger.error(f"Error listing documents: {e}")
            raise HTTPException(status_code=500, detail=f"Error listing documents: {str(e)}")
    
    if not filenames_to_process:
        return {
            "total_files": 0,
            "successful": 0,
            "failed": 0,
            "results": []
        }
    
    # Find source files for each document
    source_files_dir = os.path.join(PROJECT_ROOT, "source_files")
    ingested_dir = os.path.join(PROJECT_ROOT, "ingested_files")
    
    for filename in filenames_to_process:
        result = {"filename": filename, "status": "failed", "message": "", "chunks_added": 0}
        
        try:
            # Try to find the file in ingested_files first
            file_ext = os.path.splitext(filename)[1].lower()
            ext_without_dot = file_ext[1:] if file_ext.startswith('.') else file_ext
            
            file_found = False
            source_path = None
            
            # Check ingested_files
            ingested_path = os.path.join(ingested_dir, ext_without_dot, filename)
            if os.path.exists(ingested_path):
                source_path = ingested_path
                file_found = True
            else:
                # Check source_files
                source_path = os.path.join(source_files_dir, filename)
                if os.path.exists(source_path):
                    file_found = True
            
            if not file_found:
                result["message"] = f"Source file not found for {filename}"
                results.append(result)
                failed += 1
                continue
            
            # Schedule background reprocessing
            background_tasks.add_task(reprocess_document_in_background, filename, source_path, file_ext)
            
            result["status"] = "success"
            result["message"] = "Queued for reprocessing"
            results.append(result)
            successful += 1
            
        except Exception as e:
            logger.error(f"Error queuing reprocessing for {filename}: {e}")
            result["message"] = f"Error: {str(e)}"
            results.append(result)
            failed += 1
    
    # Invalidate cache if any documents were successfully queued for reprocessing
    # Note: Only check cache if assistant has been initialized (lazy loading)
    if successful > 0:
        try:
            assistant = get_assistant()
            if assistant.enable_query_caching and assistant.query_cache:
                cleared = assistant.query_cache.clear()
                logger.info(f"🗑️ Cache invalidated (cleared {cleared} entries) due to bulk reprocessing")
        except Exception:
            # Assistant not initialized yet, skip cache invalidation
            pass
    
    # Log audit event
    ip_address = None
    if http_request:
        ip_address = (
            http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
            http_request.headers.get("X-Real-IP", "") or
            (http_request.client.host if http_request.client else None)
        )
    log_audit_event(
        event_type="bulk_document_reprocessed",
        user_id=current_user.id,
        username=current_user.username,
        ip_address=ip_address,
        status="success" if successful > 0 else "failed",
        details={"total_files": len(filenames_to_process), "successful": successful, "failed": failed}
    )
    
    return {
        "total_files": len(filenames_to_process),
        "successful": successful,
        "failed": failed,
        "results": results
    }


@app.get("/health", response_model=HealthResponse)
async def get_health():
    """Get knowledge base health summary."""
    try:
        proc = get_processor()
        summary = HealthMonitor.get_health_summary(proc)
        return {"summary": summary}
    except Exception as e:
        logger.error(f"Error getting health summary: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting health summary: {str(e)}")


@app.get("/health/metrics", response_model=MetricsHistoryResponse)
async def get_metrics_history(metric_type: Optional[str] = None, hours: int = 24, limit: int = 100):
    """Get historical metrics."""
    try:
        metrics = HealthMonitor.get_metrics_history(metric_type=metric_type, hours=hours, limit=limit)
        return {"metrics": metrics}
    except Exception as e:
        logger.error(f"Error getting metrics history: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting metrics history: {str(e)}")


@app.get("/health/performance", response_model=PerformanceStatsResponse)
def get_performance_stats(hours: int = 24):
    """Get performance statistics for the specified time period."""
    try:
        stats_raw = HealthMonitor.get_performance_stats(hours=hours)
        if not isinstance(stats_raw, dict):
            stats_raw = {}

        # Provide defaults for missing fields (must match `PerformanceStats` / nested models)
        default_stats = {
            "period_hours": int(hours),
            "timestamp": datetime.now().isoformat(),
            "queries": {
                "total": 0,
                "last_hour": 0,
                "last_6_hours": 0,
                "throughput_per_hour": 0.0,
                "response_time": {
                    "min": 0.0,
                    "avg": 0.0,
                    "max": 0.0,
                    "p50": 0.0,
                    "p95": 0.0,
                    "p99": 0.0,
                },
                "avg_sources_per_query": 0.0,
            },
            "errors": {"total": 0, "rate_percent": 0.0, "by_type": {}},
            "document_processing": {
                "total_processed": 0,
                "successful": 0,
                "failed": 0,
                "success_rate_percent": 100.0,
                "avg_processing_time_sec": 0.0,
                "avg_chunks_per_doc": 0.0,
                "total_size_bytes": 0,
                "total_size_mb": 0.0,
            },
        }

        # Shallow + nested merges
        merged = default_stats.copy()
        merged.update(stats_raw)

        merged["queries"] = {**default_stats["queries"], **(stats_raw.get("queries") or {})}
        merged["queries"]["response_time"] = {
            **default_stats["queries"]["response_time"],
            **((merged["queries"].get("response_time") or {})),
        }
        merged["errors"] = {**default_stats["errors"], **(stats_raw.get("errors") or {})}
        merged["document_processing"] = {
            **default_stats["document_processing"],
            **(stats_raw.get("document_processing") or {}),
        }

        # Ensure by_type is dict (Pydantic expects Dict[str,int])
        if not isinstance(merged["errors"].get("by_type"), dict):
            merged["errors"]["by_type"] = {}

        # Validate shape via Pydantic and wrap in response model shape
        stats_model = PerformanceStats(**merged)
        return {"stats": stats_model}
    except Exception as e:
        logger.error(f"Error getting performance stats: {e}", exc_info=True)
        # Return default stats instead of raising error
        default_stats = {
            "period_hours": int(hours),
            "timestamp": datetime.now().isoformat(),
            "queries": {
                "total": 0,
                "last_hour": 0,
                "last_6_hours": 0,
                "throughput_per_hour": 0.0,
                "response_time": {"min": 0.0, "avg": 0.0, "max": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0},
                "avg_sources_per_query": 0.0,
            },
            "errors": {"total": 0, "rate_percent": 0.0, "by_type": {}},
            "document_processing": {
                "total_processed": 0,
                "successful": 0,
                "failed": 0,
                "success_rate_percent": 100.0,
                "avg_processing_time_sec": 0.0,
                "avg_chunks_per_doc": 0.0,
                "total_size_bytes": 0,
                "total_size_mb": 0.0,
            },
        }
        return {"stats": PerformanceStats(**default_stats)}

# Cache Management Endpoints
@app.get("/cache/stats")
def get_cache_stats():
    """Get query cache statistics."""
    try:
        assistant = get_assistant()
        if not assistant.enable_query_caching or not assistant.query_cache:
            return {
                "enabled": False,
                "message": "Query caching is not enabled"
            }
        
        stats = assistant.query_cache.get_stats()
        return {
            "enabled": True,
            **stats
        }
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/cache")
def clear_cache():
    """Clear all cached queries."""
    try:
        assistant = get_assistant()
        if not assistant.enable_query_caching or not assistant.query_cache:
            raise HTTPException(status_code=400, detail="Query caching is not enabled")
        
        cleared = assistant.query_cache.clear()
        logger.info(f"Cache cleared: {cleared} entries removed")
        return {
            "message": f"Cache cleared successfully",
            "entries_cleared": cleared
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cache/invalidate")
def invalidate_cache(pattern: str = None):
    """Invalidate cache entries matching a pattern (e.g., document name)."""
    try:
        assistant = get_assistant()
        if not assistant.enable_query_caching or not assistant.query_cache:
            raise HTTPException(status_code=400, detail="Query caching is not enabled")
        
        cleared = assistant.query_cache.invalidate(pattern)
        logger.info(f"Cache invalidated: {cleared} entries removed (pattern: {pattern or 'all'})")
        return {
            "message": f"Cache invalidated successfully",
            "entries_cleared": cleared,
            "pattern": pattern or "all"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error invalidating cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Analytics Endpoints
@app.get("/analytics/queries", response_model=QueryAnalyticsResponse)
def get_query_analytics(hours: int = 24, current_user: UserInfo = Depends(get_current_user)):
    """Get comprehensive query analytics."""
    try:
        analytics_data = AnalyticsTracker.get_query_analytics(hours=hours)
        
        # Convert to response models with error handling
        most_asked = []
        try:
            for entry in analytics_data.get("most_asked_queries", []):
                try:
                    most_asked.append(QueryAnalyticsEntry(**entry))
                except Exception as e:
                    logger.warning(f"Error parsing query analytics entry: {e}, entry: {entry}")
                    continue
        except Exception as e:
            logger.warning(f"Error parsing most asked queries: {e}")
        
        doc_usage = []
        try:
            for entry in analytics_data.get("document_usage", []):
                try:
                    doc_usage.append(DocumentUsageEntry(**entry))
                except Exception as e:
                    logger.warning(f"Error parsing document usage entry: {e}")
                    continue
        except Exception as e:
            logger.warning(f"Error parsing document usage: {e}")
        
        intent_perf = {}
        try:
            for intent, data in analytics_data.get("intent_performance", {}).items():
                try:
                    intent_perf[intent] = IntentPerformance(**data)
                except Exception as e:
                    logger.warning(f"Error parsing intent performance for {intent}: {e}")
                    continue
        except Exception as e:
            logger.warning(f"Error parsing intent performance: {e}")
        
        confidence_stats = None
        try:
            if analytics_data.get("confidence_stats"):
                confidence_stats = ConfidenceStats(**analytics_data["confidence_stats"])
        except Exception as e:
            logger.warning(f"Error parsing confidence stats: {e}")
        
        cache_perf = CachePerformance(hits=0, misses=0, hit_rate=0.0)
        try:
            cache_data = analytics_data.get("cache_performance", {})
            cache_perf = CachePerformance(**cache_data)
        except Exception as e:
            logger.warning(f"Error parsing cache performance: {e}, using defaults")
        
        verification_stats = VerificationStats(
            total_verified=0,
            supported_count=0,
            partial_count=0,
            unsupported_count=0,
            not_verified_count=0
        )
        try:
            verif_data = analytics_data.get("verification_stats", {})
            verification_stats = VerificationStats(**verif_data)
        except Exception as e:
            logger.warning(f"Error parsing verification stats: {e}, using defaults")
        
        query_trends = []
        try:
            for entry in analytics_data.get("query_trends", []):
                try:
                    query_trends.append(QueryTrendEntry(**entry))
                except Exception as e:
                    logger.warning(f"Error parsing query trend entry: {e}")
                    continue
        except Exception as e:
            logger.warning(f"Error parsing query trends: {e}")
        
        return QueryAnalyticsResponse(
            period_hours=analytics_data.get("period_hours", hours),
            total_queries=analytics_data.get("total_queries", 0),
            most_asked_queries=most_asked,
            document_usage=doc_usage,
            intent_distribution=analytics_data.get("intent_distribution", {}),
            intent_performance=intent_perf,
            confidence_stats=confidence_stats,
            cache_performance=cache_perf,
            query_trends=query_trends,
            verification_stats=verification_stats
        )
    except Exception as e:
        logger.error(f"Error getting query analytics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error loading analytics: {str(e)}")

@app.get("/analytics/knowledge-gaps", response_model=KnowledgeGapsResponse)
def get_knowledge_gaps(hours: int = 24, current_user: UserInfo = Depends(get_current_user)):
    """Identify knowledge gaps based on low confidence queries."""
    try:
        proc = get_processor()
        gaps = AnalyticsTracker.get_knowledge_gaps(proc, hours=hours)
        
        gap_objects = [KnowledgeGap(**gap) for gap in gaps]
        
        return KnowledgeGapsResponse(
            gaps=gap_objects,
            total_gaps=len(gap_objects)
        )
    except Exception as e:
        logger.error(f"Error getting knowledge gaps: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/analytics/users", response_model=UserInsightsResponse)
def get_user_insights(hours: int = 24, current_user: UserInfo = Depends(get_current_user)):
    """Get user behavior insights."""
    try:
        insights = AnalyticsTracker.get_user_insights(hours=hours)
        
        top_users = [UserActivityEntry(**user) for user in insights.get("top_users", [])]
        
        return UserInsightsResponse(
            total_active_users=insights.get("total_active_users", 0),
            top_users=top_users,
            total_user_queries=insights.get("total_user_queries", 0)
        )
    except Exception as e:
        logger.error(f"Error getting user insights: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Export & Backup Endpoints
import zipfile
import tempfile
from pathlib import Path
from fastapi.responses import FileResponse

EXPORT_DIR = os.path.join(PROJECT_ROOT, "exports")
BACKUP_DIR = os.path.join(PROJECT_ROOT, "backups")

# Ensure directories exist
os.makedirs(EXPORT_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)


@app.post("/export", response_model=ExportResponse)
def export_data(
    request: ExportRequest,
    current_user: UserInfo = Depends(get_current_user),
    http_request: FastAPIRequest = None
):
    """Export data from the system."""
    try:
        # Check permissions (only admins can export user data)
        if request.export_type == "users" and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Only admins can export user data")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_data = {}
        
        # Export documents
        if request.export_type in ["documents", "all"]:
            proc = get_processor()
            documents = proc.list_documents()
            export_data["documents"] = documents
            
            if request.include_chunks:
                # Get chunks for each document
                chunks_data = {}
                for doc in documents:
                    filename = doc.get("filename", "")
                    try:
                        results = proc.collection.get(where={"source": filename})
                        chunks_data[filename] = {
                            "chunk_count": len(results.get("ids", [])),
                            "chunks": [
                                {
                                    "id": id_,
                                    "document": doc_text,
                                    "metadata": meta
                                }
                                for id_, doc_text, meta in zip(
                                    results.get("ids", []),
                                    results.get("documents", []),
                                    results.get("metadatas", [])
                                )
                            ]
                        }
                    except Exception as e:
                        logger.warning(f"Error getting chunks for {filename}: {e}")
                        chunks_data[filename] = {"chunk_count": 0, "chunks": []}
                export_data["document_chunks"] = chunks_data
        
        # Export conversations
        if request.export_type in ["conversations", "all"]:
            try:
                conversations = ConversationManager.list_conversations()
                # Filter by date if provided
                if request.date_from or request.date_to:
                    filtered_convos = []
                    for conv in conversations:
                        conv_date = conv.get("created_at", "")
                        if request.date_from and conv_date < request.date_from:
                            continue
                        if request.date_to and conv_date > request.date_to:
                            continue
                        filtered_convos.append(conv)
                    export_data["conversations"] = filtered_convos
                else:
                    export_data["conversations"] = conversations
            except Exception as e:
                logger.warning(f"Error exporting conversations: {e}")
                export_data["conversations"] = []
        
        # Export analytics
        if request.export_type in ["analytics", "all"]:
            try:
                hours = 24 * 30  # Last 30 days
                if request.date_from or request.date_to:
                    # Calculate hours based on date range
                    if request.date_from and request.date_to:
                        from_date = datetime.fromisoformat(request.date_from.replace("Z", "+00:00"))
                        to_date = datetime.fromisoformat(request.date_to.replace("Z", "+00:00"))
                        hours = int((to_date - from_date).total_seconds() / 3600)
                
                analytics = AnalyticsTracker.get_query_analytics(hours=hours)
                export_data["analytics"] = analytics
            except Exception as e:
                logger.warning(f"Error exporting analytics: {e}")
                export_data["analytics"] = {}
        
        # Export users (admin only)
        if request.export_type in ["users", "all"] and current_user.role == "admin":
            try:
                user_manager = get_user_manager()
                users = user_manager.list_users()
                # Remove sensitive data
                safe_users = []
                for user in users:
                    safe_user = {
                        "id": user.get("id"),
                        "username": user.get("username"),
                        "email": user.get("email"),
                        "role": user.get("role"),
                        "created_at": user.get("created_at"),
                        "last_login": user.get("last_login"),
                        "is_active": user.get("is_active", True)
                    }
                    safe_users.append(safe_user)
                export_data["users"] = safe_users
            except Exception as e:
                logger.warning(f"Error exporting users: {e}")
                export_data["users"] = []
        
        # Export search history
        if request.export_type in ["all"]:
            try:
                history = SearchHistory.get_history(limit=10000)
                export_data["search_history"] = history
            except Exception as e:
                logger.warning(f"Error exporting search history: {e}")
                export_data["search_history"] = []
        
        # Create export file
        filename = f"export_{request.export_type}_{timestamp}"
        
        if request.format == "json":
            file_path = os.path.join(EXPORT_DIR, f"{filename}.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False, default=str)
        elif request.format == "csv":
            # For CSV, we'll create a zip with multiple CSV files
            file_path = os.path.join(EXPORT_DIR, f"{filename}.zip")
            with zipfile.ZipFile(file_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for key, data in export_data.items():
                    if isinstance(data, list) and len(data) > 0:
                        # Convert to CSV
                        import csv as csv_module
                        csv_data = []
                        if isinstance(data[0], dict):
                            # Get all keys from first item
                            fieldnames = list(data[0].keys())
                            csv_buffer = io.StringIO()
                            writer = csv_module.DictWriter(csv_buffer, fieldnames=fieldnames)
                            writer.writeheader()
                            for row in data:
                                # Convert dict values to strings
                                safe_row = {k: str(v) for k, v in row.items()}
                                writer.writerow(safe_row)
                            csv_data = csv_buffer.getvalue()
                            zipf.writestr(f"{key}.csv", csv_data)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {request.format}")
        
        file_size = os.path.getsize(file_path)
        
        # Log audit event
        ip_address = None
        if http_request:
            ip_address = (
                http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
                http_request.headers.get("X-Real-IP", "") or
                (http_request.client.host if http_request.client else None)
            )
        log_audit_event(
            event_type="data_exported",
            user_id=current_user.id,
            username=current_user.username,
            ip_address=ip_address,
            status="success",
            details={"export_type": request.export_type, "format": request.format, "file_size": file_size}
        )
        
        return {
            "message": f"Export created successfully",
            "file_path": file_path,
            "file_size": file_size,
            "download_url": f"/export/download/{os.path.basename(file_path)}",
            "expires_at": (datetime.now() + timedelta(days=7)).isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/export/download/{filename}")
def download_export(
    filename: str,
    current_user: UserInfo = Depends(get_current_user)
):
    """Download an exported file."""
    try:
        # Security: prevent path traversal
        safe_filename = os.path.basename(filename)
        file_path = os.path.join(EXPORT_DIR, safe_filename)
        
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Export file not found")
        
        # Check if file is in exports directory (security check)
        if not os.path.abspath(file_path).startswith(os.path.abspath(EXPORT_DIR)):
            raise HTTPException(status_code=403, detail="Invalid file path")
        
        return FileResponse(
            file_path,
            media_type="application/octet-stream",
            filename=safe_filename
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading export: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/backup/create", response_model=BackupResponse)
def create_backup(
    request: BackupRequest,
    current_user: UserInfo = Depends(get_current_user),
    http_request: FastAPIRequest = None
):
    """Create a system backup."""
    try:
        # Only admins can create backups
        if current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Only admins can create backups")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_id = f"backup_{timestamp}"
        backup_path = os.path.join(BACKUP_DIR, f"{backup_id}.zip")
        
        total_size = 0
        
        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            # Backup ChromaDB
            if request.include_chromadb:
                chromadb_path = os.path.join(PROJECT_ROOT, ".chromadb")
                if os.path.exists(chromadb_path):
                    for root, dirs, files in os.walk(chromadb_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, PROJECT_ROOT)
                            zipf.write(file_path, arcname)
                            total_size += os.path.getsize(file_path)
            
            # Backup data files
            if request.include_data:
                data_path = os.path.join(PROJECT_ROOT, "data")
                if os.path.exists(data_path):
                    for root, dirs, files in os.walk(data_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, PROJECT_ROOT)
                            zipf.write(file_path, arcname)
                            total_size += os.path.getsize(file_path)
            
            # Backup files
            if request.include_files:
                for dir_name in ["ingested_files", "source_files"]:
                    dir_path = os.path.join(PROJECT_ROOT, dir_name)
                    if os.path.exists(dir_path):
                        for root, dirs, files in os.walk(dir_path):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arcname = os.path.relpath(file_path, PROJECT_ROOT)
                                zipf.write(file_path, arcname)
                                total_size += os.path.getsize(file_path)
            
            # Add backup metadata
            metadata = {
                "backup_id": backup_id,
                "created_at": datetime.now().isoformat(),
                "created_by": current_user.username,
                "description": request.description,
                "includes": {
                    "chromadb": request.include_chromadb,
                    "data": request.include_data,
                    "files": request.include_files
                }
            }
            zipf.writestr("backup_metadata.json", json.dumps(metadata, indent=2))
        
        backup_size = os.path.getsize(backup_path)
        
        # Log audit event
        ip_address = None
        if http_request:
            ip_address = (
                http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
                http_request.headers.get("X-Real-IP", "") or
                (http_request.client.host if http_request.client else None)
            )
        log_audit_event(
            event_type="backup_created",
            user_id=current_user.id,
            username=current_user.username,
            ip_address=ip_address,
            status="success",
            details={"backup_id": backup_id, "backup_size": backup_size}
        )
        
        return {
            "message": "Backup created successfully",
            "backup_id": backup_id,
            "backup_path": backup_path,
            "backup_size": backup_size,
            "created_at": datetime.now().isoformat(),
            "includes": {
                "chromadb": request.include_chromadb,
                "data": request.include_data,
                "files": request.include_files
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating backup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/backup/list", response_model=BackupListResponse)
def list_backups(current_user: UserInfo = Depends(get_current_user)):
    """List all available backups."""
    try:
        # Only admins can list backups
        if current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Only admins can list backups")
        
        backups = []
        total_size = 0
        
        if os.path.exists(BACKUP_DIR):
            for filename in os.listdir(BACKUP_DIR):
                if filename.endswith(".zip"):
                    backup_path = os.path.join(BACKUP_DIR, filename)
                    backup_size = os.path.getsize(backup_path)
                    total_size += backup_size
                    
                    # Try to read metadata
                    description = None
                    created_at = datetime.fromtimestamp(os.path.getctime(backup_path)).isoformat()
                    includes = {"chromadb": True, "data": True, "files": True}
                    
                    try:
                        with zipfile.ZipFile(backup_path, "r") as zipf:
                            if "backup_metadata.json" in zipf.namelist():
                                metadata_str = zipf.read("backup_metadata.json").decode("utf-8")
                                metadata = json.loads(metadata_str)
                                description = metadata.get("description")
                                created_at = metadata.get("created_at", created_at)
                                includes = metadata.get("includes", includes)
                    except Exception as e:
                        logger.warning(f"Error reading backup metadata: {e}")
                    
                    backup_id = filename.replace(".zip", "")
                    backups.append({
                        "backup_id": backup_id,
                        "backup_path": backup_path,
                        "backup_size": backup_size,
                        "created_at": created_at,
                        "description": description,
                        "includes": includes
                    })
        
        # Sort by creation date (newest first)
        backups.sort(key=lambda x: x["created_at"], reverse=True)
        
        return {
            "backups": [BackupInfo(**backup) for backup in backups],
            "total_backups": len(backups),
            "total_size": total_size
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing backups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/backup/download/{backup_id}")
def download_backup(
    backup_id: str,
    current_user: UserInfo = Depends(get_current_user)
):
    """Download a backup file."""
    try:
        # Only admins can download backups
        if current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Only admins can download backups")
        
        # Security: prevent path traversal
        safe_backup_id = os.path.basename(backup_id)
        backup_path = os.path.join(BACKUP_DIR, f"{safe_backup_id}.zip")
        
        if not os.path.exists(backup_path):
            raise HTTPException(status_code=404, detail="Backup not found")
        
        # Check if file is in backups directory (security check)
        if not os.path.abspath(backup_path).startswith(os.path.abspath(BACKUP_DIR)):
            raise HTTPException(status_code=403, detail="Invalid backup path")
        
        return FileResponse(
            backup_path,
            media_type="application/zip",
            filename=f"{safe_backup_id}.zip"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading backup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/backup/restore")
def restore_backup(
    request: RestoreRequest,
    current_user: UserInfo = Depends(get_current_user),
    http_request: FastAPIRequest = None
):
    """Restore from a backup."""
    try:
        # Only admins can restore backups
        if current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Only admins can restore backups")
        
        # Security: prevent path traversal
        safe_backup_id = os.path.basename(request.backup_id)
        backup_path = os.path.join(BACKUP_DIR, f"{safe_backup_id}.zip")
        
        if not os.path.exists(backup_path):
            raise HTTPException(status_code=404, detail="Backup not found")
        
        # Check if file is in backups directory (security check)
        if not os.path.abspath(backup_path).startswith(os.path.abspath(BACKUP_DIR)):
            raise HTTPException(status_code=403, detail="Invalid backup path")
        
        # Read backup metadata
        with zipfile.ZipFile(backup_path, "r") as zipf:
            if "backup_metadata.json" in zipf.namelist():
                metadata_str = zipf.read("backup_metadata.json").decode("utf-8")
                metadata = json.loads(metadata_str)
            else:
                metadata = {}
        
        # Restore files
        restored_items = []
        
        project_root_abs = os.path.abspath(PROJECT_ROOT)
        
        with zipfile.ZipFile(backup_path, "r") as zipf:
            for file_info in zipf.filelist:
                # Skip metadata file
                if file_info.filename == "backup_metadata.json":
                    continue
                
                # Prevent Zip Slip: ensure extracted path stays within PROJECT_ROOT
                dest_path = os.path.normpath(os.path.join(PROJECT_ROOT, file_info.filename))
                dest_path_abs = os.path.abspath(dest_path)
                if not dest_path_abs.startswith(project_root_abs + os.sep) and dest_path_abs != project_root_abs:
                    logger.warning(f"Skipping Zip Slip attempt: {file_info.filename}")
                    continue
                
                # Determine what to restore based on path
                if file_info.filename.startswith(".chromadb/") and request.restore_chromadb:
                    # Restore ChromaDB
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    with zipf.open(file_info) as source, open(dest_path, "wb") as target:
                        target.write(source.read())
                    restored_items.append(file_info.filename)
                
                elif file_info.filename.startswith("data/") and request.restore_data:
                    # Restore data files
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    with zipf.open(file_info) as source, open(dest_path, "wb") as target:
                        target.write(source.read())
                    restored_items.append(file_info.filename)
                
                elif (file_info.filename.startswith("ingested_files/") or 
                      file_info.filename.startswith("source_files/")) and request.restore_files:
                    # Restore files
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    with zipf.open(file_info) as source, open(dest_path, "wb") as target:
                        target.write(source.read())
                    restored_items.append(file_info.filename)
        
        # Log audit event
        ip_address = None
        if http_request:
            ip_address = (
                http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
                http_request.headers.get("X-Real-IP", "") or
                (http_request.client.host if http_request.client else None)
            )
        log_audit_event(
            event_type="backup_restored",
            user_id=current_user.id,
            username=current_user.username,
            ip_address=ip_address,
            status="success",
            details={"backup_id": request.backup_id, "restored_items": len(restored_items)}
        )
        
        return {
            "message": f"Backup restored successfully. {len(restored_items)} items restored.",
            "backup_id": request.backup_id,
            "restored_items": len(restored_items),
            "restored_files": restored_items[:10]  # First 10 for preview
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restoring backup: {e}")
        raise HTTPException(status_code=500, detail=str(e))

