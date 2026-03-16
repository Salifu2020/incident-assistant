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
FEEDBACK_FILE = os.path.join(PROJECT_ROOT, "data", "feedback.json")
CONVERSATIONS_FILE = os.path.join(PROJECT_ROOT, "data", "conversations.json")

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


class QuerySuggestions:
    """Generate query suggestions based on history, saved queries, and document content."""
    
    # Class variable to hold assistant instance for document-based suggestions
    _assistant_instance = None
    
    @classmethod
    def set_assistant(cls, assistant):
        """Set the KnowledgeAssistant instance for document-based suggestions."""
        cls._assistant_instance = assistant
    
    @staticmethod
    def get_suggestions(partial_query: str, limit: int = 10, include_documents: bool = True) -> List[Dict]:
        """Get query suggestions based on partial input.
        
        Args:
            partial_query: The partial query text
            limit: Maximum number of suggestions to return
            include_documents: If True, include document-based suggestions
            
        Returns:
            List of suggestion dictionaries with 'query', 'type', and 'score'
        """
        suggestions = []
        partial_lower = partial_query.lower().strip()
        
        if not partial_lower:
            # If no input, mix document-based suggestions with saved queries and history
            if include_documents and QuerySuggestions._assistant_instance:
                try:
                    # Get document-based suggestions (use 40% of limit)
                    doc_suggestions = QuerySuggestions._assistant_instance.generate_document_suggestions(
                        limit=max(3, limit // 2)
                    )
                    suggestions.extend(doc_suggestions)
                except Exception as e:
                    print(f"⚠️ Error getting document suggestions: {e}")
            
            # Add saved queries (30% of limit)
            saved = SavedQueries.get_all()
            saved_sorted = sorted(
                saved,
                key=lambda x: (x.get("usage_count", 0), x.get("updated_at", "")),
                reverse=True
            )
            remaining = limit - len(suggestions)
            for item in saved_sorted[:max(2, remaining // 2)]:
                if item.get("query", "") not in [s["query"] for s in suggestions]:
                    suggestions.append({
                        "query": item.get("query", ""),
                        "type": "saved",
                        "score": 1.0,
                        "name": item.get("name", ""),
                        "usage_count": item.get("usage_count", 0)
                    })
            
            # Add recent history (remaining slots)
            history = SearchHistory.get_history(limit=max(2, limit - len(suggestions)))
            for entry in history:
                query = entry.get("query", "")
                if query and query not in [s["query"] for s in suggestions] and len(suggestions) < limit:
                    suggestions.append({
                        "query": query,
                        "type": "history",
                        "score": 0.8
                    })
            
            return suggestions[:limit]
        
        # Search in saved queries
        saved = SavedQueries.get_all()
        for item in saved:
            query = item.get("query", "").lower()
            name = item.get("name", "").lower()
            
            # Check if partial matches query or name
            if partial_lower in query or partial_lower in name:
                score = 1.0
                # Boost score if it starts with the partial
                if query.startswith(partial_lower) or name.startswith(partial_lower):
                    score = 1.2
                # Boost score based on usage
                score += min(item.get("usage_count", 0) * 0.1, 0.5)
                
                suggestions.append({
                    "query": item.get("query", ""),
                    "type": "saved",
                    "score": score,
                    "name": item.get("name", ""),
                    "usage_count": item.get("usage_count", 0)
                })
        
        # Search in history
        history = SearchHistory.get_history(limit=100)
        for entry in history:
            query = entry.get("query", "").lower()
            if partial_lower in query:
                # Don't add if already in suggestions
                if entry.get("query", "") not in [s["query"] for s in suggestions]:
                    score = 0.7
                    # Boost if starts with partial
                    if query.startswith(partial_lower):
                        score = 0.9
                    
                    suggestions.append({
                        "query": entry.get("query", ""),
                        "type": "history",
                        "score": score
                    })
        
        # Sort by score (highest first)
        suggestions.sort(key=lambda x: x["score"], reverse=True)
        
        return suggestions[:limit]
    
    @staticmethod
    def get_popular_queries(limit: int = 5) -> List[str]:
        """Get most popular queries from saved queries."""
        saved = SavedQueries.get_all()
        sorted_saved = sorted(
            saved,
            key=lambda x: x.get("usage_count", 0),
            reverse=True
        )
        return [item.get("query", "") for item in sorted_saved[:limit] if item.get("query")]


class ConversationManager:
    """Manage conversation threads and context."""
    
    @staticmethod
    def create_conversation(title: Optional[str] = None) -> Dict:
        """Create a new conversation."""
        conversations = load_json_file(CONVERSATIONS_FILE, [])
        
        conversation_id = datetime.now().isoformat().replace(":", "-").replace(".", "-")
        conversation = {
            "id": conversation_id,
            "title": title or f"Conversation {len(conversations) + 1}",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "messages": [],
            "context_enabled": True,
            "message_count": 0
        }
        
        conversations.append(conversation)
        save_json_file(CONVERSATIONS_FILE, conversations)
        return conversation
    
    @staticmethod
    def get_conversation(conversation_id: str) -> Optional[Dict]:
        """Get a conversation by ID."""
        conversations = load_json_file(CONVERSATIONS_FILE, [])
        for conv in conversations:
            if conv.get("id") == conversation_id:
                return conv
        return None
    
    @staticmethod
    def get_all_conversations() -> List[Dict]:
        """Get all conversations, sorted by most recent."""
        conversations = load_json_file(CONVERSATIONS_FILE, [])
        return sorted(conversations, key=lambda x: x.get("updated_at", ""), reverse=True)
    
    @staticmethod
    def list_conversations() -> List[Dict]:
        """Alias for get_all_conversations for backward compatibility."""
        return ConversationManager.get_all_conversations()
    
    @staticmethod
    def add_message(conversation_id: str, role: str, content: str, sources: List[Dict] = None):
        """Add a message to a conversation."""
        conversations = load_json_file(CONVERSATIONS_FILE, [])
        
        for conv in conversations:
            if conv.get("id") == conversation_id:
                message = {
                    "role": role,
                    "content": content,
                    "sources": sources or [],
                    "timestamp": datetime.now().isoformat()
                }
                conv["messages"].append(message)
                conv["message_count"] = len(conv["messages"])
                conv["updated_at"] = datetime.now().isoformat()
                
                # Auto-generate title from first user message if not set
                if conv["message_count"] == 1 and role == "user":
                    conv["title"] = content[:50] + ("..." if len(content) > 50 else "")
                
                save_json_file(CONVERSATIONS_FILE, conversations)
                return message
        
        return None
    
    @staticmethod
    def get_conversation_context(conversation_id: str, max_messages: int = 5) -> List[Dict]:
        """Get recent messages from a conversation for context."""
        conversation = ConversationManager.get_conversation(conversation_id)
        if not conversation:
            return []
        
        messages = conversation.get("messages", [])
        # Get last max_messages exchanges (user + assistant pairs)
        recent = messages[-max_messages * 2:] if len(messages) > max_messages * 2 else messages
        
        # Format for LLM context
        context = []
        for msg in recent:
            context.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })
        
        return context
    
    @staticmethod
    def update_conversation(conversation_id: str, title: Optional[str] = None, context_enabled: Optional[bool] = None):
        """Update conversation metadata."""
        conversations = load_json_file(CONVERSATIONS_FILE, [])
        
        for conv in conversations:
            if conv.get("id") == conversation_id:
                if title is not None:
                    conv["title"] = title
                if context_enabled is not None:
                    conv["context_enabled"] = context_enabled
                conv["updated_at"] = datetime.now().isoformat()
                save_json_file(CONVERSATIONS_FILE, conversations)
                return conv
        
        return None
    
    @staticmethod
    def delete_conversation(conversation_id: str):
        """Delete a conversation."""
        conversations = load_json_file(CONVERSATIONS_FILE, [])
        conversations = [c for c in conversations if c.get("id") != conversation_id]
        save_json_file(CONVERSATIONS_FILE, conversations)
    
    @staticmethod
    def clear_conversation(conversation_id: str):
        """Clear all messages from a conversation."""
        conversations = load_json_file(CONVERSATIONS_FILE, [])
        
        for conv in conversations:
            if conv.get("id") == conversation_id:
                conv["messages"] = []
                conv["message_count"] = 0
                conv["updated_at"] = datetime.now().isoformat()
                save_json_file(CONVERSATIONS_FILE, conversations)
                return conv
        
        return None


class AnswerFeedback:
    """Manage answer quality feedback."""
    
    @staticmethod
    def add_feedback(
        query: str,
        response: str,
        rating: int,  # 1-5 stars or -1 (thumbs down), 1 (thumbs up)
        feedback_type: str = "rating",  # "rating", "thumbs", "detailed"
        comment: Optional[str] = None,
        sources_count: int = 0
    ):
        """Add feedback for an answer."""
        feedback = load_json_file(FEEDBACK_FILE, [])
        
        entry = {
            "query": query,
            "response_preview": response[:200] if response else "",  # Store preview
            "rating": rating,
            "feedback_type": feedback_type,
            "comment": comment or "",
            "sources_count": sources_count,
            "timestamp": datetime.now().isoformat()
        }
        
        feedback.append(entry)
        save_json_file(FEEDBACK_FILE, feedback)
        return entry
    
    @staticmethod
    def get_feedback(limit: Optional[int] = None) -> List[Dict]:
        """Get all feedback entries."""
        feedback = load_json_file(FEEDBACK_FILE, [])
        if limit:
            return feedback[:limit]
        return feedback
    
    @staticmethod
    def get_feedback_stats() -> Dict:
        """Get feedback statistics."""
        feedback = AnswerFeedback.get_feedback()
        
        if not feedback:
            return {
                "total": 0,
                "average_rating": 0.0,
                "thumbs_up": 0,
                "thumbs_down": 0,
                "ratings_distribution": {}
            }
        
        ratings = [f.get("rating", 0) for f in feedback if f.get("feedback_type") == "rating" and f.get("rating", 0) > 0]
        thumbs_up = len([f for f in feedback if f.get("rating") == 1 and f.get("feedback_type") == "thumbs"])
        thumbs_down = len([f for f in feedback if f.get("rating") == -1 and f.get("feedback_type") == "thumbs"])
        
        # Rating distribution
        distribution = {}
        for rating in ratings:
            distribution[rating] = distribution.get(rating, 0) + 1
        
        average_rating = sum(ratings) / len(ratings) if ratings else 0.0
        
        return {
            "total": len(feedback),
            "average_rating": round(average_rating, 2),
            "thumbs_up": thumbs_up,
            "thumbs_down": thumbs_down,
            "ratings_distribution": distribution,
            "positive_feedback": thumbs_up + len([r for r in ratings if r >= 4]),
            "negative_feedback": thumbs_down + len([r for r in ratings if r <= 2])
        }
    
    @staticmethod
    def get_feedback_by_query(query: str) -> Optional[Dict]:
        """Get feedback for a specific query."""
        feedback = AnswerFeedback.get_feedback()
        # Find most recent feedback for this query
        for entry in reversed(feedback):
            if entry.get("query") == query:
                return entry
        return None

