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

# Get project root directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USERS_FILE = os.path.join(PROJECT_ROOT, "data", "users.json")

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

