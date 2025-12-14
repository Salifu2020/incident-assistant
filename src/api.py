from fastapi import FastAPI, File, UploadFile, HTTPException, Request, BackgroundTasks, Depends, status, Request as FastAPIRequest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional
import os
import logging
import shutil
import json
import asyncio
from logging.handlers import RotatingFileHandler
from datetime import timedelta, datetime

from .dependencies import processor, assistant
from .models import (
    QuestionRequest, QuestionResponse, UploadResponse,
    DocumentListResponse, DocumentInfo, DeleteDocumentResponse,
    HistoryResponse, HistoryEntry, SavedQueriesResponse, SavedQuery,
    SaveQueryRequest, UpdateSavedQueryRequest,
    SuggestionsResponse, QuerySuggestion,
    FeedbackRequest, FeedbackResponse, FeedbackEntry, FeedbackStats, FeedbackStatsResponse,
    Conversation, ConversationListResponse, ConversationMessage,
    CreateConversationRequest, UpdateConversationRequest,
    AdvancedSearchFilters, AdvancedQuestionRequest,
    HealthSummary, HealthResponse, MetricEntry, MetricsHistoryResponse,
    PerformanceStats, PerformanceStatsResponse,
    UserRegister, UserLogin, UserInfo, Token, TokenData, UserListResponse,
    ChangePasswordRequest, UpdateUserRoleRequest,
    PasswordResetRequest, PasswordResetVerifyRequest, PasswordResetConfirmRequest,
    PasswordResetResponse,
    TwoFASetupResponse, TwoFAVerifyRequest, TwoFALoginRequest, TwoFAResponse,
    SessionInfo, SessionListResponse, RefreshTokenRequest, TokenRefreshResponse,
    AuditLogEntry, AuditLogResponse, AuditLogFilter,
    UserPreferences, ProfileUpdateRequest, PreferencesUpdateRequest, ProfileResponse
)
from .history import SearchHistory, SavedQueries, QuerySuggestions, AnswerFeedback, ConversationManager
from .health import HealthMonitor
from .auth import (
    UserManager, verify_token, create_access_token, create_refresh_token,
    verify_refresh_token, create_session, update_session_activity,
    revoke_session, revoke_all_user_sessions, get_user_sessions,
    get_session_by_token, cleanup_expired_sessions, load_sessions, save_sessions,
    log_audit_event, load_audit_logs,
    SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS,
    AVATARS_DIR
)

# Import email service (optional - will work without it)
try:
    from .email_service import EmailService
except ImportError:
    EmailService = None
    logger.warning("Email service not available. Install aiosmtplib, email-validator, and jinja2 for email support.")

# Get project root directory (parent of src)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Logging Configuration
log_dir = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(log_dir, exist_ok=True)
log_file_path = os.path.join(log_dir, "api.log")

file_handler = RotatingFileHandler(log_file_path, maxBytes=1_000_000, backupCount=3)
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), file_handler],
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Knowledge Assistant API")

# Allow CORS (adjust for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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
    user = UserManager.get_user_by_id(user_id)
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

@app.on_event("startup")
def startup_event():
    logger.info("🚀 FastAPI app is starting...")
    # Initialize default admin user if no users exist
    try:
        if UserManager.initialize_default_admin():
            logger.info("✅ Default admin user created (username: admin, password: admin123)")
    except Exception as e:
        logger.warning(f"Could not initialize default admin: {e}")

@app.get("/")
def root():
    return {"message": "📚 Knowledge Assistant API is running"}

# Authentication endpoints
@app.post("/auth/register", response_model=UserInfo)
async def register(user_data: UserRegister):
    """Register a new user."""
    try:
        # Validate role
        if user_data.role not in ["user", "admin"]:
            raise HTTPException(status_code=400, detail="Invalid role. Must be 'user' or 'admin'")
        
        user = UserManager.create_user(
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
    result = UserManager.authenticate_user(credentials.username, credentials.password)
    
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
        user = UserManager.get_user_by_id(user_id)
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
    users = UserManager.list_users()
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
    success = UserManager.update_user_role(user_id, role_data.role)
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
    
    success = UserManager.deactivate_user(user_id)
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
    
    success = UserManager.activate_user(user_id)
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
    
    success = UserManager.unlock_account(user_id)
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
    user = UserManager.get_user_by_username(username)
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
    user = UserManager.get_user_by_id(user_id)
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
    
    # Generate filename
    ext = os.path.splitext(file.filename)[1] or ".jpg"
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
def get_status():
    """Get status of the knowledge base."""
    try:
        collection_count = processor.collection.count()
        
        # Get list of unique documents
        try:
            # Sample some chunks to get document names
            sample = processor.collection.get(limit=min(100, collection_count))
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
            "message": f"Knowledge base contains {collection_count} chunks from {len(documents)} document(s)"
        }
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return {
            "status": "error",
            "error": str(e)
        }

@app.get("/documents", response_model=DocumentListResponse)
def list_documents():
    """List all documents in the knowledge base with details."""
    try:
        documents = processor.list_documents()
        total_chunks = processor.collection.count()
        
        return {
            "documents": documents,
            "total_documents": len(documents),
            "total_chunks": total_chunks
        }
    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents/{filename}", response_model=DocumentInfo)
def get_document_info(filename: str):
    """Get detailed information about a specific document."""
    try:
        doc_info = processor.get_document_info(filename)
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
        deleted_count, error = processor.delete_document(filename)
        
        if error:
            raise HTTPException(status_code=404, detail=error)
        
        logger.info(f"Deleted {deleted_count} chunks for document '{filename}'")
        
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
def get_suggestions(q: str = "", limit: int = 10):
    """Get query suggestions based on partial input."""
    try:
        suggestions_data = QuerySuggestions.get_suggestions(q, limit=limit)
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
        entry = AnswerFeedback.add_feedback(
            query=payload.query,
            response=payload.response,
            rating=payload.rating,
            feedback_type=payload.feedback_type,
            comment=payload.comment,
            sources_count=payload.sources_count
        )
        logger.info(f"Feedback submitted: rating={payload.rating}, type={payload.feedback_type}")
        return {
            "message": "Feedback submitted successfully",
            "feedback_id": entry.get("timestamp", "")
        }
    except Exception as e:
        logger.error(f"Error submitting feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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

@app.post("/ask", response_model=QuestionResponse)
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
        answer, sources = await loop.run_in_executor(
            None, 
            assistant.ask_question, 
            payload.query,
            payload.document_filters,
            conversation_context,
            None  # advanced_filters - will be None for regular requests
        )
        
        elapsed_time = time.time() - start_time
        logger.info(f"Response generated ({len(answer)} chars) with {len(sources)} sources in {elapsed_time:.2f}s")
        
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
        
        return {"response": answer, "sources": sources}
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
            start_time = time.time()
            
            # Get conversation context if conversation_id is provided
            conversation_context = []
            is_followup = False
            if payload.conversation_id:
                conversation_context = ConversationManager.get_conversation_context(
                    payload.conversation_id,
                    max_messages=5
                )
                is_followup = len(conversation_context) > 0
            
            # Enhance query for follow-up questions
            enhanced_query = payload.query
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
                    enhanced_query = f"{payload.query} [Context: {context_hint}]"
            
            # Retrieve context first (synchronous operation)
            loop = asyncio.get_event_loop()
            context, sources = await loop.run_in_executor(
                None,
                assistant.retrieve_context,
                enhanced_query if is_followup else payload.query,
                4,  # k value
                payload.document_filters
            )
            
            if not context:
                # Send error message
                error_msg = "⚠️ No relevant information found in the knowledge base."
                yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"
                return
            
            # Send sources first
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
            
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
            
            # Stream the response with follow-up awareness
            response_text = ""
            for chunk in assistant.generate_response_stream(payload.query, context, is_followup=is_followup):
                response_text += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
            
            # Send completion signal
            yield f"data: {json.dumps({'type': 'done', 'full_response': response_text.strip()})}\n\n"
            
            # Record query metric
            try:
                response_time = time.time() - start_time
                HealthMonitor.record_query(payload.query, response_time, len(sources), success=True)
            except Exception as e:
                logger.warning(f"Failed to record query metric: {e}")
            
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
            logger.error(f"Error in streaming: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': f'❌ Error: {str(e)}'})}\n\n"
    
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
        
        # Get initial chunk count
        initial_count = processor.collection.count()
        logger.info(f"📊 Knowledge base before processing: {initial_count} chunks")
        
        # Run the ingestion processor (this may move the file itself)
        processor.process_document(source_path)
        
        # Verify chunks were added
        final_count = processor.collection.count()
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


@app.get("/health", response_model=HealthResponse)
async def get_health():
    """Get knowledge base health summary."""
    try:
        summary = HealthMonitor.get_health_summary(processor)
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
async def get_performance_stats(hours: int = 24):
    """Get performance statistics."""
    try:
        stats = HealthMonitor.get_performance_stats(hours=hours)
        return {"stats": stats}
    except Exception as e:
        logger.error(f"Error getting performance stats: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting performance stats: {str(e)}")
