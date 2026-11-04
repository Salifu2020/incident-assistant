"""
Database-backed user authentication (PostgreSQL).
This module provides the same interface as auth.py but uses PostgreSQL instead of JSON files.
"""
from .database import get_db, User, is_db_available, init_db
from .auth import (
    hash_password, verify_password, validate_password,
    create_access_token, create_refresh_token, verify_token, verify_refresh_token,
    log_audit_event, normalize_email, generate_username_from_email
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
        first_name = getattr(user, "first_name", None)
        display_name = getattr(user, "display_name", None) or first_name
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "active": user.active,
            "first_name": first_name,
            "display_name": display_name,
        }
    
    @staticmethod
    def create_user(
        email: str,
        password: str,
        role: str = "user",
        first_name: Optional[str] = None,
        username: Optional[str] = None,
    ) -> Dict:
        """Create a new user in database. Username is auto-generated when omitted."""
        # Validate password policy
        is_valid, errors = validate_password(password)
        if not is_valid:
            raise ValueError("Password does not meet requirements: " + "; ".join(errors))

        email = normalize_email(email)
        if not email or "@" not in email:
            raise ValueError("A valid email address is required")
        first_name = (first_name or "").strip() or None

        db = get_db()
        if db is None:
            raise RuntimeError("Database not available")
        
        try:
            existing_email = db.query(User).filter(User.email == email).first()
            if existing_email:
                raise ValueError("Email already exists")

            if not username:
                existing_usernames = {u.username for u in db.query(User.username).all()}
                username = generate_username_from_email(email, existing_usernames)
            else:
                existing_username = db.query(User).filter(User.username == username).first()
                if existing_username:
                    raise ValueError("Username already exists")
            
            # Hash password
            hashed_password = hash_password(password)
            
            # Create new user
            now = datetime.utcnow()
            user_kwargs = dict(
                id=secrets.token_urlsafe(16),
                username=username,
                email=email,
                hashed_password=hashed_password,
                role=role,
                created_at=now,
                password_changed_at=now,
                last_login=None,
                active=True,
            )
            # Optional columns may not exist on older DBs; set when present on model
            if hasattr(User, "first_name"):
                user_kwargs["first_name"] = first_name
            if hasattr(User, "display_name"):
                user_kwargs["display_name"] = first_name

            new_user = User(**user_kwargs)
            
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            
            logger.info(f"Created new user in database: {email}")
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
    def get_user_by_email(email: str) -> Optional[Dict]:
        """Get user by email."""
        db = get_db()
        if db is None:
            return None

        try:
            user = db.query(User).filter(User.email == normalize_email(email)).first()
            if user:
                result = DBUserManager._user_to_dict(user)
                result["hashed_password"] = user.hashed_password
                result["password_changed_at"] = (
                    user.password_changed_at.isoformat() if user.password_changed_at else None
                )
                return result
            return None
        except Exception as e:
            logger.error(f"Error getting user by email: {e}")
            return None
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
                result = DBUserManager._user_to_dict(user)
                result["hashed_password"] = user.hashed_password
                result["password_changed_at"] = (
                    user.password_changed_at.isoformat() if user.password_changed_at else None
                )
                return result
            return None
        except Exception as e:
            logger.error(f"Error getting user by username: {e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def authenticate_user(email: str, password: str) -> Optional[Dict]:
        """Authenticate user by email and return user info if successful."""
        user_dict = DBUserManager.get_user_by_email(email)
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
                "last_login": datetime.utcnow().isoformat(),
                "first_name": user_dict.get("first_name"),
                "display_name": user_dict.get("display_name") or user_dict.get("first_name"),
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
                        email="admin@example.com",
                        password="REDACTED",
                        role="admin",
                        first_name="Admin",
                        username="admin",
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

