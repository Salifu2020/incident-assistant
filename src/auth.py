"""
User authentication and authorization system.
"""
import os
import json
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import threading
from jose import JWTError, jwt
from passlib.context import CryptContext
import logging

logger = logging.getLogger(__name__)

# Get project root directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USERS_FILE = os.path.join(PROJECT_ROOT, "data", "users.json")
RESET_TOKENS_FILE = os.path.join(PROJECT_ROOT, "data", "reset_tokens.json")
RATE_LIMIT_FILE = os.path.join(PROJECT_ROOT, "data", "rate_limits.json")

# Thread lock for file operations
_file_lock = threading.Lock()

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


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
        users_data = load_users()
        users = users_data.get("users", [])
        
        # Check if username or email already exists
        for user in users:
            if user.get("username") == username:
                raise ValueError("Username already exists")
            if user.get("email") == email:
                raise ValueError("Email already exists")
        
        # Create new user
        new_user = {
            "id": secrets.token_urlsafe(16),
            "username": username,
            "email": email,
            "hashed_password": hash_password(password),
            "role": role,
            "created_at": datetime.now().isoformat(),
            "last_login": None,
            "active": True
        }
        
        users.append(new_user)
        users_data["users"] = users
        save_users(users_data)
        
        return {
            "id": new_user["id"],
            "username": new_user["username"],
            "email": new_user["email"],
            "role": new_user["role"],
            "created_at": new_user["created_at"]
        }
    
    @staticmethod
    def authenticate_user(username: str, password: str) -> Optional[Dict]:
        """Authenticate a user and return user info if successful."""
        users_data = load_users()
        users = users_data.get("users", [])
        
        for user in users:
            if user.get("username") == username and user.get("active", True):
                if verify_password(password, user.get("hashed_password", "")):
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
        return None
    
    @staticmethod
    def get_user_by_id(user_id: str) -> Optional[Dict]:
        """Get user by ID."""
        users_data = load_users()
        users = users_data.get("users", [])
        
        for user in users:
            if user.get("id") == user_id:
                return {
                    "id": user["id"],
                    "username": user["username"],
                    "email": user["email"],
                    "role": user["role"],
                    "created_at": user.get("created_at"),
                    "last_login": user.get("last_login"),
                    "active": user.get("active", True)
                }
        return None
    
    @staticmethod
    def get_user_by_username(username: str) -> Optional[Dict]:
        """Get user by username."""
        users_data = load_users()
        users = users_data.get("users", [])
        
        for user in users:
            if user.get("username") == username:
                return {
                    "id": user["id"],
                    "username": user["username"],
                    "email": user["email"],
                    "role": user["role"],
                    "created_at": user.get("created_at"),
                    "last_login": user.get("last_login"),
                    "active": user.get("active", True)
                }
        return None
    
    @staticmethod
    def list_users() -> List[Dict]:
        """List all users (admin only)."""
        users_data = load_users()
        users = users_data.get("users", [])
        
        return [
            {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": user["role"],
                "created_at": user.get("created_at"),
                "last_login": user.get("last_login"),
                "active": user.get("active", True)
            }
            for user in users
        ]
    
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
    def change_password(user_id: str, old_password: str, new_password: str) -> bool:
        """Change user password."""
        users_data = load_users()
        users = users_data.get("users", [])
        
        for user in users:
            if user.get("id") == user_id:
                if verify_password(old_password, user.get("hashed_password", "")):
                    user["hashed_password"] = hash_password(new_password)
                    save_users(users_data)
                    return True
                else:
                    return False
        return False
    
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
    def reset_password_with_token(token: str, new_password: str) -> bool:
        """Reset password using a reset token."""
        token_info = UserManager.verify_reset_token(token)
        if not token_info:
            return False
        
        user_id = token_info["user_id"]
        users_data = load_users()
        users = users_data.get("users", [])
        
        for user in users:
            if user.get("id") == user_id:
                user["hashed_password"] = hash_password(new_password)
                save_users(users_data)
                
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
                
                return True
        
        return False
    
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

