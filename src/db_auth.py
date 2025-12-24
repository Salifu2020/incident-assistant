"""
Database-backed user authentication (PostgreSQL).
This module provides the same interface as auth.py but uses PostgreSQL instead of JSON files.
"""
from .database import get_db, User, is_db_available, init_db
from .auth import (
    hash_password, verify_password, validate_password,
    create_access_token, create_refresh_token, verify_token, verify_refresh_token,
    log_audit_event
)
from typing import Dict, Optional, Tuple, List
from datetime import datetime
import secrets
import logging

logger = logging.getLogger(__name__)

class DBUserManager:
    """Database-backed user manager."""
    
    @staticmethod
    def _user_to_dict(user: User) -> Dict:
        """Convert User model to dictionary."""
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "active": user.active
        }
    
    @staticmethod
    def create_user(username: str, email: str, password: str, role: str = "user") -> Dict:
        """Create a new user in database."""
        # Validate password policy
        is_valid, errors = validate_password(password)
        if not is_valid:
            raise ValueError("Password does not meet requirements: " + "; ".join(errors))
        
        db = get_db()
        if db is None:
            raise RuntimeError("Database not available")
        
        try:
            # Check if username or email already exists
            existing_user = db.query(User).filter(
                (User.username == username) | (User.email == email)
            ).first()
            
            if existing_user:
                if existing_user.username == username:
                    raise ValueError("Username already exists")
                if existing_user.email == email:
                    raise ValueError("Email already exists")
            
            # Hash password
            hashed_password = hash_password(password)
            
            # Create new user
            now = datetime.utcnow()
            new_user = User(
                id=secrets.token_urlsafe(16),
                username=username,
                email=email,
                hashed_password=hashed_password,
                role=role,
                created_at=now,
                password_changed_at=now,
                last_login=None,
                active=True
            )
            
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            
            logger.info(f"Created new user in database: {username}")
            return DBUserManager._user_to_dict(new_user)
            
        except ValueError:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating user: {e}")
            raise RuntimeError(f"Failed to create user: {str(e)}")
        finally:
            db.close()
    
    @staticmethod
    def get_user_by_username(username: str) -> Optional[Dict]:
        """Get user by username."""
        db = get_db()
        if db is None:
            return None
        
        try:
            user = db.query(User).filter(User.username == username).first()
            if user:
                return {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "hashed_password": user.hashed_password,
                    "role": user.role,
                    "created_at": user.created_at.isoformat() if user.created_at else None,
                    "password_changed_at": user.password_changed_at.isoformat() if user.password_changed_at else None,
                    "last_login": user.last_login.isoformat() if user.last_login else None,
                    "active": user.active
                }
            return None
        except Exception as e:
            logger.error(f"Error getting user by username: {e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def authenticate_user(username: str, password: str) -> Optional[Dict]:
        """Authenticate user and return user info if successful."""
        user_dict = DBUserManager.get_user_by_username(username)
        if not user_dict:
            return None
        
        if not user_dict.get("active", True):
            return None
        
        if verify_password(password, user_dict.get("hashed_password", "")):
            # Update last login
            db = get_db()
            if db:
                try:
                    user = db.query(User).filter(User.id == user_dict["id"]).first()
                    if user:
                        user.last_login = datetime.utcnow()
                        db.commit()
                except Exception as e:
                    logger.error(f"Error updating last login: {e}")
                finally:
                    db.close()
            
            # Return user info (without password)
            return {
                "id": user_dict["id"],
                "username": user_dict["username"],
                "email": user_dict["email"],
                "role": user_dict["role"],
                "created_at": user_dict["created_at"],
                "last_login": datetime.utcnow().isoformat()
            }
        
        return None
    
    @staticmethod
    def get_user_by_id(user_id: str) -> Optional[Dict]:
        """Get user by ID."""
        db = get_db()
        if db is None:
            return None
        
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                return DBUserManager._user_to_dict(user)
            return None
        except Exception as e:
            logger.error(f"Error getting user by ID: {e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def initialize_default_admin() -> bool:
        """Initialize default admin user if no users exist."""
        db = get_db()
        if db is None:
            return False
        
        try:
            user_count = db.query(User).count()
            if user_count == 0:
                try:
                    DBUserManager.create_user(
                        username="admin",
                        email="admin@example.com",
                        password="REDACTED",
                        role="admin"
                    )
                    logger.info("✅ Default admin user created in database")
                    return True
                except ValueError as e:
                    logger.error(f"Failed to create default admin: {e}")
                    return False
            return False
        except Exception as e:
            logger.error(f"Error checking/creating default admin: {e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def get_all_users() -> List[Dict]:
        """Get all users (admin function)."""
        db = get_db()
        if db is None:
            return []
        
        try:
            users = db.query(User).all()
            return [DBUserManager._user_to_dict(user) for user in users]
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []
        finally:
            db.close()
    
    @staticmethod
    def list_users() -> List[Dict]:
        """List all users (alias for get_all_users)."""
        return DBUserManager.get_all_users()
    
    @staticmethod
    def update_user_role(user_id: str, role: str) -> bool:
        """Update user role."""
        db = get_db()
        if db is None:
            return False
        
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.role = role
                db.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating user role: {e}")
            db.rollback()
            return False
        finally:
            db.close()
    
    @staticmethod
    def activate_user(user_id: str) -> bool:
        """Activate a user."""
        db = get_db()
        if db is None:
            return False
        
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.active = True
                db.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Error activating user: {e}")
            db.rollback()
            return False
        finally:
            db.close()
    
    @staticmethod
    def deactivate_user(user_id: str) -> bool:
        """Deactivate a user."""
        db = get_db()
        if db is None:
            return False
        
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.active = False
                db.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Error deactivating user: {e}")
            db.rollback()
            return False
        finally:
            db.close()
    
    @staticmethod
    def unlock_account(user_id: str) -> bool:
        """Unlock account (placeholder - account locking not yet implemented in DB)."""
        # TODO: Implement account locking in database
        # For now, just return True
        return True

