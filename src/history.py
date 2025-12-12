"""
Search history and saved queries management.
"""
import os
import json
from datetime import datetime
from typing import List, Dict, Optional
import threading

# Get project root directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_FILE = os.path.join(PROJECT_ROOT, "data", "search_history.json")
SAVED_QUERIES_FILE = os.path.join(PROJECT_ROOT, "data", "saved_queries.json")

# Thread lock for file operations
_file_lock = threading.Lock()


def ensure_data_dir():
    """Ensure the data directory exists."""
    data_dir = os.path.join(PROJECT_ROOT, "data")
    os.makedirs(data_dir, exist_ok=True)


def load_json_file(file_path: str, default: List) -> List:
    """Load JSON file, returning default if file doesn't exist."""
    ensure_data_dir()
    if not os.path.exists(file_path):
        return default.copy()
    
    try:
        with _file_lock:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, list) else default.copy()
    except (json.JSONDecodeError, IOError) as e:
        print(f"⚠️ Error loading {file_path}: {e}")
        return default.copy()


def save_json_file(file_path: str, data: List):
    """Save data to JSON file."""
    ensure_data_dir()
    try:
        with _file_lock:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
    except IOError as e:
        print(f"❌ Error saving {file_path}: {e}")
        raise


class SearchHistory:
    """Manage search history."""
    
    MAX_HISTORY_ITEMS = 100  # Keep last 100 queries
    
    @staticmethod
    def add_query(query: str, response_length: int = 0, sources_count: int = 0):
        """Add a query to search history."""
        history = SearchHistory.get_history()
        
        # Add new entry
        entry = {
            "query": query,
            "timestamp": datetime.now().isoformat(),
            "response_length": response_length,
            "sources_count": sources_count
        }
        history.insert(0, entry)  # Add to beginning
        
        # Keep only last MAX_HISTORY_ITEMS
        history = history[:SearchHistory.MAX_HISTORY_ITEMS]
        
        save_json_file(HISTORY_FILE, history)
    
    @staticmethod
    def get_history(limit: Optional[int] = None) -> List[Dict]:
        """Get search history, optionally limited."""
        history = load_json_file(HISTORY_FILE, [])
        if limit:
            return history[:limit]
        return history
    
    @staticmethod
    def clear_history():
        """Clear all search history."""
        save_json_file(HISTORY_FILE, [])
    
    @staticmethod
    def delete_history_item(timestamp: str):
        """Delete a specific history item by timestamp."""
        history = SearchHistory.get_history()
        history = [h for h in history if h.get("timestamp") != timestamp]
        save_json_file(HISTORY_FILE, history)


class SavedQueries:
    """Manage saved queries."""
    
    @staticmethod
    def save_query(query: str, name: Optional[str] = None, description: Optional[str] = None):
        """Save a query."""
        saved = SavedQueries.get_all()
        
        # Check if query already exists
        for item in saved:
            if item.get("query") == query:
                # Update existing
                if name:
                    item["name"] = name
                if description:
                    item["description"] = description
                item["updated_at"] = datetime.now().isoformat()
                save_json_file(SAVED_QUERIES_FILE, saved)
                return item
        
        # Create new saved query
        entry = {
            "query": query,
            "name": name or query[:50],  # Use query as name if not provided
            "description": description or "",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "usage_count": 0
        }
        saved.append(entry)
        save_json_file(SAVED_QUERIES_FILE, saved)
        return entry
    
    @staticmethod
    def get_all() -> List[Dict]:
        """Get all saved queries."""
        return load_json_file(SAVED_QUERIES_FILE, [])
    
    @staticmethod
    def get_by_query(query: str) -> Optional[Dict]:
        """Get a saved query by query text."""
        saved = SavedQueries.get_all()
        for item in saved:
            if item.get("query") == query:
                return item
        return None
    
    @staticmethod
    def increment_usage(query: str):
        """Increment usage count for a saved query."""
        saved = SavedQueries.get_all()
        for item in saved:
            if item.get("query") == query:
                item["usage_count"] = item.get("usage_count", 0) + 1
                item["updated_at"] = datetime.now().isoformat()
                save_json_file(SAVED_QUERIES_FILE, saved)
                break
    
    @staticmethod
    def delete_saved_query(query: str):
        """Delete a saved query."""
        saved = SavedQueries.get_all()
        saved = [s for s in saved if s.get("query") != query]
        save_json_file(SAVED_QUERIES_FILE, saved)
    
    @staticmethod
    def update_saved_query(query: str, name: Optional[str] = None, description: Optional[str] = None):
        """Update a saved query."""
        saved = SavedQueries.get_all()
        for item in saved:
            if item.get("query") == query:
                if name is not None:
                    item["name"] = name
                if description is not None:
                    item["description"] = description
                item["updated_at"] = datetime.now().isoformat()
                save_json_file(SAVED_QUERIES_FILE, saved)
                return item
        return None

