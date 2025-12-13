"""
User authentication and authorization system.
"""
import os
import json
import hashlib
import secrets
import base64
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple
import threading
from jose import JWTError, jwt
from passlib.context import CryptContext
import logging
import pyotp
import qrcode
from io import BytesIO

logger = logging.getLogger(__name__)

# Get project root directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USERS_FILE = os.path.join(PROJECT_ROOT, "data", "users.json")
RESET_TOKENS_FILE = os.path.join(PROJECT_ROOT, "data", "reset_tokens.json")
RATE_LIMIT_FILE = os.path.join(PROJECT_ROOT, "data", "rate_limits.json")
LOCKOUT_FILE = os.path.join(PROJECT_ROOT, "data", "account_lockouts.json")
PASSWORD_HISTORY_FILE = os.path.join(PROJECT_ROOT, "data", "password_history.json")
TWOFA_FILE = os.path.join(PROJECT_ROOT, "data", "twofa.json")
SESSIONS_FILE = os.path.join(PROJECT_ROOT, "data", "sessions.json")
AUDIT_LOG_FILE = os.path.join(PROJECT_ROOT, "data", "audit_log.json")

# Lockout configuration
MAX_FAILED_ATTEMPTS = 5  # Lock after 5 failed attempts
LOCKOUT_DURATION_MINUTES = 30  # Auto-unlock after 30 minutes

# Password policy configuration
PASSWORD_MIN_LENGTH = 8
PASSWORD_REQUIRE_UPPERCASE = True
PASSWORD_REQUIRE_LOWERCASE = True
PASSWORD_REQUIRE_NUMBER = True
PASSWORD_REQUIRE_SPECIAL = True
PASSWORD_HISTORY_COUNT = 5  # Prevent reusing last 5 passwords
PASSWORD_EXPIRATION_DAYS = 90  # Passwords expire after 90 days (0 = disabled)

# Thread lock for file operations
_file_lock = threading.Lock()

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
REFRESH_TOKEN_EXPIRE_DAYS = 30  # 30 days
SESSION_TIMEOUT_MINUTES = 60 * 24 * 7  # 7 days of inactivity


def ensure_data_dir():
    """Ensure data directory exists."""
    data_dir = os.path.dirname(USERS_FILE)
    os.makedirs(data_dir, exist_ok=True)


def load_users() -> Dict:
    """Load users from JSON file."""
    ensure_data_dir()
    with _file_lock:
        if os.path.exists(USERS_FILE):
            try:
                with open(USERS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {"users": []}
        return {"users": []}


def save_users(data: Dict):
    """Save users to JSON file."""
    ensure_data_dir()
    with _file_lock:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def load_reset_tokens() -> Dict:
    """Load password reset tokens from JSON file."""
    ensure_data_dir()
    with _file_lock:
        if os.path.exists(RESET_TOKENS_FILE):
            try:
                with open(RESET_TOKENS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {"tokens": []}
        return {"tokens": []}


def save_reset_tokens(data: Dict):
    """Save password reset tokens to JSON file."""
    ensure_data_dir()
    with _file_lock:
        with open(RESET_TOKENS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def load_rate_limits() -> Dict:
    """Load rate limit data from JSON file."""
    ensure_data_dir()
    with _file_lock:
        if os.path.exists(RATE_LIMIT_FILE):
            try:
                with open(RATE_LIMIT_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {"limits": []}
        return {"limits": []}


def save_rate_limits(data: Dict):
    """Save rate limit data to JSON file."""
    ensure_data_dir()
    with _file_lock:
        with open(RATE_LIMIT_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def load_lockouts() -> Dict:
    """Load account lockout data from JSON file."""
    ensure_data_dir()
    with _file_lock:
        if os.path.exists(LOCKOUT_FILE):
            try:
                with open(LOCKOUT_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {"lockouts": []}
        return {"lockouts": []}


def save_lockouts(data: Dict):
    """Save account lockout data to JSON file."""
    ensure_data_dir()
    with _file_lock:
        with open(LOCKOUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def generate_user_friendly_token() -> str:
    """Generate a shorter, user-friendly token."""
    # Generate 8-character alphanumeric token (case-insensitive for user convenience)
    import string
    import random
    # Use uppercase letters and numbers, exclude confusing characters (0, O, I, 1)
    chars = string.ascii_uppercase.replace('O', '').replace('I', '') + '23456789'
    token = ''.join(random.choice(chars) for _ in range(8))
    # Add a hyphen for readability: XXXX-XXXX
    return f"{token[:4]}-{token[4:]}"


def hash_password(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


def validate_password(password: str) -> Tuple[bool, List[str]]:
    """
    Validate password against policy.
    Returns (is_valid, list_of_errors).
    """
    errors = []
    
    # Minimum length
    if len(password) < PASSWORD_MIN_LENGTH:
        errors.append(f"Password must be at least {PASSWORD_MIN_LENGTH} characters long")
    
    # Complexity requirements
    if PASSWORD_REQUIRE_UPPERCASE and not any(c.isupper() for c in password):
        errors.append("Password must contain at least one uppercase letter")
    
    if PASSWORD_REQUIRE_LOWERCASE and not any(c.islower() for c in password):
        errors.append("Password must contain at least one lowercase letter")
    
    if PASSWORD_REQUIRE_NUMBER and not any(c.isdigit() for c in password):
        errors.append("Password must contain at least one number")
    
    if PASSWORD_REQUIRE_SPECIAL:
        special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
        if not any(c in special_chars for c in password):
            errors.append("Password must contain at least one special character (!@#$%^&*()_+-=[]{}|;:,.<>?)")
    
    return len(errors) == 0, errors


def load_password_history() -> Dict:
    """Load password history data from JSON file."""
    ensure_data_dir()
    with _file_lock:
        if os.path.exists(PASSWORD_HISTORY_FILE):
            try:
                with open(PASSWORD_HISTORY_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {"history": []}
        return {"history": []}


def save_password_history(data: Dict):
    """Save password history data to JSON file."""
    ensure_data_dir()
    with _file_lock:
        with open(PASSWORD_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def check_password_history(user_id: str, new_password: str) -> bool:
    """
    Check if password was used recently.
    Returns True if password is in history (should be rejected).
    """
    history_data = load_password_history()
    history = history_data.get("history", [])
    
    user_history = [h for h in history if h.get("user_id") == user_id]
    user_history.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    # Check against last N passwords
    for hist_entry in user_history[:PASSWORD_HISTORY_COUNT]:
        old_hash = hist_entry.get("hashed_password", "")
        if verify_password(new_password, old_hash):
            return True  # Password was used before
    
    return False  # Password is new


def add_to_password_history(user_id: str, hashed_password: str):
    """Add a password hash to the user's password history."""
    history_data = load_password_history()
    history = history_data.get("history", [])
    
    # Add new entry
    history.append({
        "user_id": user_id,
        "hashed_password": hashed_password,
        "created_at": datetime.now().isoformat()
    })
    
    # Keep only recent history for this user (last N + 1 to account for current)
    user_history = [h for h in history if h.get("user_id") == user_id]
    user_history.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    # Remove old entries beyond history count
    if len(user_history) > PASSWORD_HISTORY_COUNT + 1:
        keep_ids = {h.get("created_at") for h in user_history[:PASSWORD_HISTORY_COUNT + 1]}
        history = [h for h in history if not (h.get("user_id") == user_id and h.get("created_at") not in keep_ids)]
    
    history_data["history"] = history
    save_password_history(history_data)


def check_password_expiration(user_id: str) -> Tuple[bool, Optional[str]]:
    """
    Check if user's password has expired.
    Returns (is_expired, expiration_date).
    """
    if PASSWORD_EXPIRATION_DAYS == 0:
        return False, None  # Password expiration disabled
    
    users_data = load_users()
    users = users_data.get("users", [])
    
    for user in users:
        if user.get("id") == user_id:
            password_changed_at = user.get("password_changed_at")
            if not password_changed_at:
                # If password was never changed, use created_at
                password_changed_at = user.get("created_at")
            
            if password_changed_at:
                try:
                    changed_date = datetime.fromisoformat(password_changed_at)
                    expiration_date = changed_date + timedelta(days=PASSWORD_EXPIRATION_DAYS)
                    
                    if datetime.now() >= expiration_date:
                        return True, expiration_date.isoformat()
                    else:
                        return False, expiration_date.isoformat()
                except Exception:
                    pass
    
    return False, None


def load_twofa() -> Dict:
    """Load 2FA data from JSON file."""
    ensure_data_dir()
    with _file_lock:
        if os.path.exists(TWOFA_FILE):
            try:
                with open(TWOFA_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {"users": []}
        return {"users": []}


def save_twofa(data: Dict):
    """Save 2FA data to JSON file."""
    ensure_data_dir()
    with _file_lock:
        with open(TWOFA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def generate_backup_codes(count: int = 10) -> List[str]:
    """Generate backup codes for 2FA recovery."""
    codes = []
    for _ in range(count):
        # Generate 8-character alphanumeric codes
        code = secrets.token_urlsafe(8).upper()[:8]
        codes.append(code)
    return codes


def generate_2fa_secret() -> str:
    """Generate a new TOTP secret."""
    return pyotp.random_base32()


def generate_2fa_qr_code(secret: str, username: str, issuer: str = "Knowledge Assistant") -> str:
    """
    Generate QR code data URI for 2FA setup.
    Returns base64-encoded PNG image data URI.
    """
    # Create TOTP URI
    totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=username,
        issuer_name=issuer
    )
    
    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(totp_uri)
    qr.make(fit=True)
    
    # Create image
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    img_str = base64.b64encode(buffer.getvalue()).decode()
    
    return f"data:image/png;base64,{img_str}"


def verify_2fa_code(secret: str, code: str) -> bool:
    """Verify a TOTP code against a secret."""
    try:
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)  # Allow 1 time step window
    except Exception:
        return False


def verify_backup_code(user_id: str, code: str) -> bool:
    """Verify and consume a backup code."""
    twofa_data = load_twofa()
    users = twofa_data.get("users", [])
    
    for user_data in users:
        if user_data.get("user_id") == user_id:
            backup_codes = user_data.get("backup_codes", [])
            # Check if code exists and hasn't been used
            for backup_code in backup_codes:
                if backup_code.get("code") == code.upper() and not backup_code.get("used", False):
                    # Mark as used
                    backup_code["used"] = True
                    backup_code["used_at"] = datetime.now().isoformat()
                    save_twofa(twofa_data)
                    logger.info(f"Backup code used for user: {user_id}")
                    return True
    
    return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(user_id: str) -> str:
    """Create a refresh token."""
    to_encode = {
        "sub": user_id,
        "type": "refresh",
        "exp": datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_refresh_token(token: str) -> Optional[str]:
    """Verify a refresh token and return user_id if valid."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") == "refresh":
            return payload.get("sub")
    except JWTError:
        pass
    return None


def load_sessions() -> Dict:
    """Load session data from JSON file."""
    ensure_data_dir()
    with _file_lock:
        if os.path.exists(SESSIONS_FILE):
            try:
                with open(SESSIONS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {"sessions": []}
        return {"sessions": []}


def save_sessions(data: Dict):
    """Save session data to JSON file."""
    ensure_data_dir()
    with _file_lock:
        with open(SESSIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def create_session(
    user_id: str,
    access_token: str,
    refresh_token: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    device_info: Optional[str] = None
) -> str:
    """Create a new session and return session ID."""
    sessions_data = load_sessions()
    sessions = sessions_data.get("sessions", [])
    
    session_id = secrets.token_urlsafe(32)
    now = datetime.now()
    
    session = {
        "session_id": session_id,
        "user_id": user_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "device_info": device_info,
        "created_at": now.isoformat(),
        "last_activity": now.isoformat(),
        "active": True
    }
    
    sessions.append(session)
    sessions_data["sessions"] = sessions
    save_sessions(sessions_data)
    
    logger.info(f"Session created for user: {user_id}")
    return session_id


def update_session_activity(session_id: str):
    """Update last activity timestamp for a session."""
    sessions_data = load_sessions()
    sessions = sessions_data.get("sessions", [])
    
    for session in sessions:
        if session.get("session_id") == session_id:
            session["last_activity"] = datetime.now().isoformat()
            save_sessions(sessions_data)
            return True
    
    return False


def revoke_session(session_id: str) -> bool:
    """Revoke a session."""
    sessions_data = load_sessions()
    sessions = sessions_data.get("sessions", [])
    
    for session in sessions:
        if session.get("session_id") == session_id:
            session["active"] = False
            session["revoked_at"] = datetime.now().isoformat()
            save_sessions(sessions_data)
            logger.info(f"Session revoked: {session_id}")
            return True
    
    return False


def revoke_all_user_sessions(user_id: str, exclude_session_id: Optional[str] = None):
    """Revoke all sessions for a user, optionally excluding one."""
    sessions_data = load_sessions()
    sessions = sessions_data.get("sessions", [])
    
    revoked_count = 0
    for session in sessions:
        if (session.get("user_id") == user_id and 
            session.get("active", False) and
            session.get("session_id") != exclude_session_id):
            session["active"] = False
            session["revoked_at"] = datetime.now().isoformat()
            revoked_count += 1
    
    if revoked_count > 0:
        save_sessions(sessions_data)
        logger.info(f"Revoked {revoked_count} sessions for user: {user_id}")
    
    return revoked_count


def get_user_sessions(user_id: str) -> List[Dict]:
    """Get all active sessions for a user."""
    sessions_data = load_sessions()
    sessions = sessions_data.get("sessions", [])
    
    user_sessions = []
    now = datetime.now()
    
    for session in sessions:
        if session.get("user_id") == user_id and session.get("active", False):
            # Check if session has timed out
            last_activity = datetime.fromisoformat(session.get("last_activity", ""))
            timeout_threshold = now - timedelta(minutes=SESSION_TIMEOUT_MINUTES)
            
            if last_activity < timeout_threshold:
                # Session timed out, mark as inactive
                session["active"] = False
                session["expired_at"] = now.isoformat()
            else:
                user_sessions.append({
                    "session_id": session.get("session_id"),
                    "ip_address": session.get("ip_address"),
                    "user_agent": session.get("user_agent"),
                    "device_info": session.get("device_info"),
                    "created_at": session.get("created_at"),
                    "last_activity": session.get("last_activity"),
                    "is_current": False  # Will be set by caller
                })
    
    # Save any changes
    save_sessions(sessions_data)
    
    return user_sessions


def get_session_by_token(access_token: str) -> Optional[Dict]:
    """Get session by access token."""
    sessions_data = load_sessions()
    sessions = sessions_data.get("sessions", [])
    
    for session in sessions:
        if session.get("access_token") == access_token and session.get("active", False):
            # Check if session has timed out
            last_activity = datetime.fromisoformat(session.get("last_activity", ""))
            timeout_threshold = datetime.now() - timedelta(minutes=SESSION_TIMEOUT_MINUTES)
            
            if last_activity < timeout_threshold:
                session["active"] = False
                session["expired_at"] = datetime.now().isoformat()
                save_sessions(sessions_data)
                return None
            
            return session
    
    return None


def cleanup_expired_sessions():
    """Remove expired sessions (call periodically)."""
    sessions_data = load_sessions()
    sessions = sessions_data.get("sessions", [])
    
    now = datetime.now()
    timeout_threshold = now - timedelta(minutes=SESSION_TIMEOUT_MINUTES)
    refresh_expiry = now - timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    original_count = len(sessions)
    
    # Remove expired sessions
    active_sessions = []
    for session in sessions:
        if not session.get("active", False):
            continue
        
        last_activity = datetime.fromisoformat(session.get("last_activity", ""))
        created_at = datetime.fromisoformat(session.get("created_at", ""))
        
        # Check activity timeout
        if last_activity < timeout_threshold:
            continue
        
        # Check refresh token expiry
        if created_at < refresh_expiry:
            continue
        
        active_sessions.append(session)
    
    if len(active_sessions) < original_count:
        sessions_data["sessions"] = active_sessions
        save_sessions(sessions_data)
        logger.info(f"Cleaned up {original_count - len(active_sessions)} expired sessions")


def verify_token(token: str) -> Optional[Dict]:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


class UserManager:
    """Manage users and authentication."""
    
    @staticmethod
    def create_user(username: str, email: str, password: str, role: str = "user") -> Dict:
        """Create a new user."""
        # Validate password policy
        is_valid, errors = validate_password(password)
        if not is_valid:
            raise ValueError("Password does not meet requirements: " + "; ".join(errors))
        
        users_data = load_users()
        users = users_data.get("users", [])
        
        # Check if username or email already exists
        for user in users:
            if user.get("username") == username:
                raise ValueError("Username already exists")
            if user.get("email") == email:
                raise ValueError("Email already exists")
        
        # Hash password
        hashed_password = hash_password(password)
        
        # Create new user
        now = datetime.now().isoformat()
        new_user = {
            "id": secrets.token_urlsafe(16),
            "username": username,
            "email": email,
            "hashed_password": hashed_password,
            "role": role,
            "created_at": now,
            "password_changed_at": now,  # Track password change date
            "last_login": None,
            "active": True
        }
        
        users.append(new_user)
        users_data["users"] = users
        save_users(users_data)
        
        # Add to password history
        add_to_password_history(new_user["id"], hashed_password)
        
        return {
            "id": new_user["id"],
            "username": new_user["username"],
            "email": new_user["email"],
            "role": new_user["role"],
            "created_at": new_user["created_at"]
        }
    
    @staticmethod
    def is_account_locked(user_id: str) -> Tuple[bool, Optional[str]]:
        """Check if account is locked. Returns (is_locked, unlock_time)."""
        lockouts_data = load_lockouts()
        lockouts = lockouts_data.get("lockouts", [])
        
        for lockout in lockouts:
            if lockout.get("user_id") == user_id and lockout.get("locked", False):
                unlock_time = datetime.fromisoformat(lockout.get("unlock_at", ""))
                if datetime.now() < unlock_time:
                    # Still locked
                    return True, unlock_time.isoformat()
                else:
                    # Lockout expired, remove it
                    lockout["locked"] = False
                    save_lockouts(lockouts_data)
                    return False, None
        
        return False, None
    
    @staticmethod
    def record_failed_login(username: str) -> Tuple[bool, Optional[str], int]:
        """Record a failed login attempt. Returns (is_locked, unlock_time, attempts_remaining)."""
        users_data = load_users()
        users = users_data.get("users", [])
        
        # Find user
        user = None
        for u in users:
            if u.get("username") == username:
                user = u
                break
        
        if not user:
            # User doesn't exist, don't track attempts (security best practice)
            return False, None, MAX_FAILED_ATTEMPTS
        
        user_id = user["id"]
        lockouts_data = load_lockouts()
        lockouts = lockouts_data.get("lockouts", [])
        
        # Find or create lockout record
        lockout = None
        for l in lockouts:
            if l.get("user_id") == user_id:
                lockout = l
                break
        
        if not lockout:
            lockout = {
                "user_id": user_id,
                "username": username,
                "failed_attempts": 0,
                "locked": False,
                "locked_at": None,
                "unlock_at": None,
                "last_attempt": None
            }
            lockouts.append(lockout)
        
        # Increment failed attempts
        lockout["failed_attempts"] = lockout.get("failed_attempts", 0) + 1
        lockout["last_attempt"] = datetime.now().isoformat()
        
        attempts = lockout["failed_attempts"]
        attempts_remaining = max(0, MAX_FAILED_ATTEMPTS - attempts)
        
        # Lock account if threshold reached
        if attempts >= MAX_FAILED_ATTEMPTS:
            lockout["locked"] = True
            lockout["locked_at"] = datetime.now().isoformat()
            unlock_time = datetime.now() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
            lockout["unlock_at"] = unlock_time.isoformat()
            logger.warning(f"Account locked: {username} after {attempts} failed attempts")
            save_lockouts(lockouts_data)
            return True, unlock_time.isoformat(), 0
        
        save_lockouts(lockouts_data)
        return False, None, attempts_remaining
    
    @staticmethod
    def clear_failed_attempts(user_id: str):
        """Clear failed login attempts (on successful login)."""
        lockouts_data = load_lockouts()
        lockouts = lockouts_data.get("lockouts", [])
        
        for lockout in lockouts:
            if lockout.get("user_id") == user_id:
                lockout["failed_attempts"] = 0
                lockout["locked"] = False
                lockout["locked_at"] = None
                lockout["unlock_at"] = None
                break
        
        save_lockouts(lockouts_data)
    
    @staticmethod
    def unlock_account(user_id: str) -> bool:
        """Manually unlock an account (admin function)."""
        lockouts_data = load_lockouts()
        lockouts = lockouts_data.get("lockouts", [])
        
        for lockout in lockouts:
            if lockout.get("user_id") == user_id:
                lockout["locked"] = False
                lockout["failed_attempts"] = 0
                lockout["locked_at"] = None
                lockout["unlock_at"] = None
                save_lockouts(lockouts_data)
                logger.info(f"Account unlocked: {lockout.get('username')}")
                return True
        
        return False
    
    @staticmethod
    def authenticate_user(username: str, password: str) -> Optional[Dict]:
        """Authenticate a user and return user info if successful."""
        users_data = load_users()
        users = users_data.get("users", [])
        
        for user in users:
            if user.get("username") == username and user.get("active", True):
                user_id = user["id"]
                
                # Check if account is locked
                is_locked, unlock_time = UserManager.is_account_locked(user_id)
                if is_locked:
                    logger.warning(f"Login attempt blocked: {username} (account locked)")
                    return {
                        "error": "account_locked",
                        "unlock_time": unlock_time
                    }
                
                if verify_password(password, user.get("hashed_password", "")):
                    # Successful login - clear failed attempts
                    UserManager.clear_failed_attempts(user_id)
                    
                    # Update last login
                    user["last_login"] = datetime.now().isoformat()
                    save_users(users_data)
                    
                    return {
                        "id": user["id"],
                        "username": user["username"],
                        "email": user["email"],
                        "role": user["role"],
                        "created_at": user.get("created_at"),
                        "last_login": user["last_login"]
                    }
                else:
                    # Failed login - record attempt
                    is_locked, unlock_time, attempts_remaining = UserManager.record_failed_login(username)
                    if is_locked:
                        return {
                            "error": "account_locked",
                            "unlock_time": unlock_time
                        }
                    return {
                        "error": "invalid_credentials",
                        "attempts_remaining": attempts_remaining
                    }
        
        # User doesn't exist - don't reveal this (security best practice)
        # But still record attempt to prevent enumeration
        UserManager.record_failed_login(username)
        return None
    
    @staticmethod
    def get_user_by_id(user_id: str) -> Optional[Dict]:
        """Get user by ID."""
        users_data = load_users()
        users = users_data.get("users", [])
        
        for user in users:
            if user.get("id") == user_id:
                # Get lockout status
                is_locked, unlock_time = UserManager.is_account_locked(user_id)
                
                # Get failed attempts count
                lockouts_data = load_lockouts()
                lockouts = lockouts_data.get("lockouts", [])
                failed_attempts = 0
                for lockout in lockouts:
                    if lockout.get("user_id") == user_id:
                        failed_attempts = lockout.get("failed_attempts", 0)
                        break
                
                # Check password expiration
                password_expired, password_expires_at = check_password_expiration(user_id)
                
                return {
                    "id": user["id"],
                    "username": user["username"],
                    "email": user["email"],
                    "role": user["role"],
                    "created_at": user.get("created_at"),
                    "last_login": user.get("last_login"),
                    "active": user.get("active", True),
                    "locked": is_locked,
                    "unlock_time": unlock_time,
                    "failed_attempts": failed_attempts,
                    "password_expires_at": password_expires_at,
                    "password_expired": password_expired
                }
        return None
    
    @staticmethod
    def get_user_by_username(username: str) -> Optional[Dict]:
        """Get user by username."""
        users_data = load_users()
        users = users_data.get("users", [])
        
        for user in users:
            if user.get("username") == username:
                user_id = user["id"]
                # Get lockout status
                is_locked, unlock_time = UserManager.is_account_locked(user_id)
                
                # Get failed attempts count
                lockouts_data = load_lockouts()
                lockouts = lockouts_data.get("lockouts", [])
                failed_attempts = 0
                for lockout in lockouts:
                    if lockout.get("user_id") == user_id:
                        failed_attempts = lockout.get("failed_attempts", 0)
                        break
                
                # Check password expiration
                password_expired, password_expires_at = check_password_expiration(user_id)
                
                return {
                    "id": user["id"],
                    "username": user["username"],
                    "email": user["email"],
                    "role": user["role"],
                    "created_at": user.get("created_at"),
                    "last_login": user.get("last_login"),
                    "active": user.get("active", True),
                    "locked": is_locked,
                    "unlock_time": unlock_time,
                    "failed_attempts": failed_attempts,
                    "password_expires_at": password_expires_at,
                    "password_expired": password_expired
                }
        return None
    
    @staticmethod
    def list_users() -> List[Dict]:
        """List all users (admin only)."""
        users_data = load_users()
        users = users_data.get("users", [])
        lockouts_data = load_lockouts()
        lockouts = lockouts_data.get("lockouts", [])
        
        # Create lookup for lockout info
        lockout_map = {}
        for lockout in lockouts:
            user_id = lockout.get("user_id")
            is_locked, unlock_time = UserManager.is_account_locked(user_id)
            lockout_map[user_id] = {
                "locked": is_locked,
                "unlock_time": unlock_time,
                "failed_attempts": lockout.get("failed_attempts", 0)
            }
        
        result = []
        for user in users:
            user_id = user["id"]
            lockout_info = lockout_map.get(user_id, {
                "locked": False,
                "unlock_time": None,
                "failed_attempts": 0
            })
            
            # Check password expiration
            password_expired, password_expires_at = check_password_expiration(user_id)
            
            # Check 2FA status
            twofa_enabled = UserManager.is_2fa_enabled(user_id)
            
            result.append({
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": user["role"],
                "created_at": user.get("created_at"),
                "last_login": user.get("last_login"),
                "active": user.get("active", True),
                "locked": lockout_info["locked"],
                "unlock_time": lockout_info["unlock_time"],
                "failed_attempts": lockout_info["failed_attempts"],
                "password_expires_at": password_expires_at,
                "password_expired": password_expired,
                "twofa_enabled": twofa_enabled
            })
        
        return result
    
    @staticmethod
    def update_user_role(user_id: str, new_role: str) -> bool:
        """Update user role (admin only)."""
        users_data = load_users()
        users = users_data.get("users", [])
        
        for user in users:
            if user.get("id") == user_id:
                user["role"] = new_role
                save_users(users_data)
                return True
        return False
    
    @staticmethod
    def deactivate_user(user_id: str) -> bool:
        """Deactivate a user (admin only)."""
        users_data = load_users()
        users = users_data.get("users", [])
        
        for user in users:
            if user.get("id") == user_id:
                user["active"] = False
                save_users(users_data)
                return True
        return False
    
    @staticmethod
    def activate_user(user_id: str) -> bool:
        """Activate a user (admin only)."""
        users_data = load_users()
        users = users_data.get("users", [])
        
        for user in users:
            if user.get("id") == user_id:
                user["active"] = True
                save_users(users_data)
                return True
        return False
    
    @staticmethod
    def change_password(user_id: str, old_password: str, new_password: str) -> Tuple[bool, Optional[str]]:
        """
        Change user password.
        Returns (success, error_message).
        """
        # Validate password policy
        is_valid, errors = validate_password(new_password)
        if not is_valid:
            return False, "Password does not meet requirements: " + "; ".join(errors)
        
        # Check password history
        if check_password_history(user_id, new_password):
            return False, f"Password cannot be reused. You must use a password different from your last {PASSWORD_HISTORY_COUNT} passwords."
        
        users_data = load_users()
        users = users_data.get("users", [])
        
        for user in users:
            if user.get("id") == user_id:
                if verify_password(old_password, user.get("hashed_password", "")):
                    # Add old password to history before changing
                    add_to_password_history(user_id, user.get("hashed_password", ""))
                    
                    # Update password
                    user["hashed_password"] = hash_password(new_password)
                    user["password_changed_at"] = datetime.now().isoformat()
                    save_users(users_data)
                    
                    # Add new password to history
                    add_to_password_history(user_id, user["hashed_password"])
                    
                    logger.info(f"Password changed for user: {user.get('username')}")
                    return True, None
                else:
                    return False, "Current password is incorrect"
        return False, "User not found"
    
    @staticmethod
    def initialize_default_admin():
        """Initialize default admin user if no users exist."""
        users_data = load_users()
        users = users_data.get("users", [])
        
        if len(users) == 0:
            # Create default admin user
            default_admin = {
                "id": "admin-default",
                "username": "admin",
                "email": "admin@example.com",
                "hashed_password": hash_password("admin123"),  # Change this in production!
                "role": "admin",
                "created_at": datetime.now().isoformat(),
                "last_login": None,
                "active": True
            }
            users.append(default_admin)
            users_data["users"] = users
            save_users(users_data)
            return True
        return False
    
    @staticmethod
    def generate_reset_token(email: str, ip_address: Optional[str] = None) -> Optional[str]:
        """Generate a password reset token for a user."""
        users_data = load_users()
        users = users_data.get("users", [])
        
        # Find user by email
        user = None
        for u in users:
            if u.get("email") == email and u.get("active", True):
                user = u
                break
        
        if not user:
            # Don't reveal if email exists or not (security best practice)
            # But still record rate limit to prevent enumeration
            UserManager.record_rate_limit(email, ip_address)
            return None
        
        # Check rate limit
        if not UserManager.check_rate_limit(email, ip_address):
            logger.warning(f"Rate limit exceeded for password reset: {email}")
            return None
        
        # Generate user-friendly token (8 characters with hyphen: XXXX-XXXX)
        token = generate_user_friendly_token()
        expires_at = datetime.now() + timedelta(minutes=30)  # 30 minute expiration
        
        # Record rate limit
        UserManager.record_rate_limit(email, ip_address)
        
        # Store token
        tokens_data = load_reset_tokens()
        tokens = tokens_data.get("tokens", [])
        
        # Remove any existing tokens for this user
        tokens = [t for t in tokens if t.get("user_id") != user["id"]]
        
        # Add new token
        tokens.append({
            "token": token,
            "user_id": user["id"],
            "email": email,
            "created_at": datetime.now().isoformat(),
            "expires_at": expires_at.isoformat(),
            "used": False
        })
        
        tokens_data["tokens"] = tokens
        save_reset_tokens(tokens_data)
        
        return token
    
    @staticmethod
    def verify_reset_token(token: str) -> Optional[Dict]:
        """Verify a password reset token and return user info if valid."""
        tokens_data = load_reset_tokens()
        tokens = tokens_data.get("tokens", [])
        
        # Normalize token (remove hyphens, convert to uppercase for comparison)
        normalized_token = token.replace('-', '').upper()
        
        for token_data in tokens:
            # Compare normalized tokens (case-insensitive, ignore hyphens)
            stored_token = token_data.get("token", "").replace('-', '').upper()
            if (stored_token == normalized_token and 
                not token_data.get("used", False)):
                
                # Check expiration
                expires_at = datetime.fromisoformat(token_data.get("expires_at", ""))
                if datetime.now() > expires_at:
                    # Token expired, mark as used
                    token_data["used"] = True
                    save_reset_tokens(tokens_data)
                    return None
                
                # Get user info
                user = UserManager.get_user_by_id(token_data.get("user_id"))
                if user:
                    return {
                        "user_id": user["id"],
                        "email": token_data.get("email"),
                        "token": token
                    }
        
        return None
    
    @staticmethod
    def reset_password_with_token(token: str, new_password: str) -> Tuple[bool, Optional[str]]:
        """
        Reset password using a reset token.
        Returns (success, error_message).
        """
        token_info = UserManager.verify_reset_token(token)
        if not token_info:
            return False, "Invalid or expired reset token"
        
        # Validate password policy
        is_valid, errors = validate_password(new_password)
        if not is_valid:
            return False, "Password does not meet requirements: " + "; ".join(errors)
        
        user_id = token_info["user_id"]
        
        # Check password history
        if check_password_history(user_id, new_password):
            return False, f"Password cannot be reused. You must use a password different from your last {PASSWORD_HISTORY_COUNT} passwords."
        
        users_data = load_users()
        users = users_data.get("users", [])
        
        for user in users:
            if user.get("id") == user_id:
                # Add old password to history before changing
                add_to_password_history(user_id, user.get("hashed_password", ""))
                
                # Update password
                user["hashed_password"] = hash_password(new_password)
                user["password_changed_at"] = datetime.now().isoformat()
                save_users(users_data)
                
                # Add new password to history
                add_to_password_history(user_id, user["hashed_password"])
                
                # Mark token as used (match normalized)
                tokens_data = load_reset_tokens()
                tokens = tokens_data.get("tokens", [])
                normalized_token = token.replace('-', '').upper()
                for t in tokens:
                    stored_token = t.get("token", "").replace('-', '').upper()
                    if stored_token == normalized_token:
                        t["used"] = True
                        break
                save_reset_tokens(tokens_data)
                
                logger.info(f"Password reset for user: {user.get('username')}")
                return True, None
        
        return False, "User not found"
    
    @staticmethod
    def cleanup_expired_tokens():
        """Remove expired reset tokens (call periodically)."""
        tokens_data = load_reset_tokens()
        tokens = tokens_data.get("tokens", [])
        
        now = datetime.now()
        valid_tokens = []
        
        for token_data in tokens:
            expires_at = datetime.fromisoformat(token_data.get("expires_at", ""))
            if expires_at > now and not token_data.get("used", False):
                valid_tokens.append(token_data)
        
        tokens_data["tokens"] = valid_tokens
        save_reset_tokens(tokens_data)
    
    @staticmethod
    def is_2fa_enabled(user_id: str) -> bool:
        """Check if 2FA is enabled for a user."""
        twofa_data = load_twofa()
        users = twofa_data.get("users", [])
        
        for user_data in users:
            if user_data.get("user_id") == user_id:
                return user_data.get("enabled", False)
        
        return False
    
    @staticmethod
    def get_2fa_secret(user_id: str) -> Optional[str]:
        """Get 2FA secret for a user (if exists)."""
        twofa_data = load_twofa()
        users = twofa_data.get("users", [])
        
        for user_data in users:
            if user_data.get("user_id") == user_id:
                return user_data.get("secret")
        
        return None
    
    @staticmethod
    def setup_2fa(user_id: str, username: str) -> Tuple[str, str, List[str]]:
        """
        Setup 2FA for a user.
        Returns (secret, qr_code_data_uri, backup_codes).
        """
        twofa_data = load_twofa()
        users = twofa_data.get("users", [])
        
        # Remove existing entry if any
        users = [u for u in users if u.get("user_id") != user_id]
        
        # Generate new secret
        secret = generate_2fa_secret()
        backup_codes = generate_backup_codes(10)
        
        # Generate QR code
        qr_code_uri = generate_2fa_qr_code(secret, username)
        
        # Store (but don't enable yet - user needs to verify first)
        users.append({
            "user_id": user_id,
            "secret": secret,
            "enabled": False,
            "setup_at": datetime.now().isoformat(),
            "backup_codes": [{"code": code, "used": False} for code in backup_codes]
        })
        
        twofa_data["users"] = users
        save_twofa(twofa_data)
        
        logger.info(f"2FA setup initiated for user: {username}")
        return secret, qr_code_uri, backup_codes
    
    @staticmethod
    def verify_and_enable_2fa(user_id: str, code: str) -> Tuple[bool, Optional[str]]:
        """
        Verify 2FA code and enable 2FA if valid.
        Returns (success, error_message).
        """
        twofa_data = load_twofa()
        users = twofa_data.get("users", [])
        
        for user_data in users:
            if user_data.get("user_id") == user_id:
                secret = user_data.get("secret")
                if not secret:
                    return False, "2FA not set up for this user"
                
                # Verify code
                if verify_2fa_code(secret, code):
                    # Enable 2FA
                    user_data["enabled"] = True
                    user_data["enabled_at"] = datetime.now().isoformat()
                    save_twofa(twofa_data)
                    logger.info(f"2FA enabled for user: {user_id}")
                    return True, None
                else:
                    return False, "Invalid verification code"
        
        return False, "2FA not set up for this user"
    
    @staticmethod
    def verify_2fa_login(user_id: str, code: str) -> bool:
        """
        Verify 2FA code during login.
        Also accepts backup codes.
        """
        twofa_data = load_twofa()
        users = twofa_data.get("users", [])
        
        for user_data in users:
            if user_data.get("user_id") == user_id:
                if not user_data.get("enabled", False):
                    return False  # 2FA not enabled
                
                secret = user_data.get("secret")
                
                # Try TOTP code first
                if secret and verify_2fa_code(secret, code):
                    return True
                
                # Try backup code
                if verify_backup_code(user_id, code):
                    return True
                
                return False
        
        return False
    
    @staticmethod
    def disable_2fa(user_id: str) -> bool:
        """Disable 2FA for a user."""
        twofa_data = load_twofa()
        users = twofa_data.get("users", [])
        
        for user_data in users:
            if user_data.get("user_id") == user_id:
                user_data["enabled"] = False
                user_data["disabled_at"] = datetime.now().isoformat()
                save_twofa(twofa_data)
                logger.info(f"2FA disabled for user: {user_id}")
                return True
        
        return False
    
    @staticmethod
    def get_backup_codes(user_id: str) -> Optional[List[str]]:
        """Get unused backup codes for a user."""
        twofa_data = load_twofa()
        users = twofa_data.get("users", [])
        
        for user_data in users:
            if user_data.get("user_id") == user_id:
                backup_codes = user_data.get("backup_codes", [])
                unused = [bc.get("code") for bc in backup_codes if not bc.get("used", False)]
                return unused
        
        return None
    
    @staticmethod
    def regenerate_backup_codes(user_id: str) -> List[str]:
        """Regenerate backup codes for a user."""
        twofa_data = load_twofa()
        users = twofa_data.get("users", [])
        
        new_codes = generate_backup_codes(10)
        
        for user_data in users:
            if user_data.get("user_id") == user_id:
                user_data["backup_codes"] = [{"code": code, "used": False} for code in new_codes]
                user_data["backup_codes_regenerated_at"] = datetime.now().isoformat()
                save_twofa(twofa_data)
                logger.info(f"Backup codes regenerated for user: {user_id}")
                return new_codes
        
        return []

