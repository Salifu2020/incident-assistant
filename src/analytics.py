"""
Advanced analytics tracking for comprehensive insights.
"""
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import Counter, defaultdict
import threading

# Get project root directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYTICS_FILE = os.path.join(PROJECT_ROOT, "data", "analytics.json")

# Thread lock for file operations
_file_lock = threading.Lock()


def ensure_data_dir():
    """Ensure data directory exists."""
    data_dir = os.path.dirname(ANALYTICS_FILE)
    os.makedirs(data_dir, exist_ok=True)


def load_json_file(filepath: str, default: any = None):
    """Load JSON file with thread safety."""
    ensure_data_dir()
    with _file_lock:
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return default if default is not None else {}
        return default if default is not None else {}


def save_json_file(filepath: str, data: any):
    """Save JSON file with thread safety."""
    ensure_data_dir()
    with _file_lock:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


class AnalyticsTracker:
    """Track comprehensive analytics for insights and optimization."""
    
    @staticmethod
    def record_query_analytics(
        query: str,
        response_time: float,
        sources: List[Dict],
        intent: Optional[str] = None,
        confidence: Optional[float] = None,
        verification_status: Optional[str] = None,
        cache_hit: bool = False,
        user_id: Optional[str] = None
    ):
        """Record detailed query analytics."""
        analytics = load_json_file(ANALYTICS_FILE, {
            "queries": [],
            "document_usage": {},
            "query_patterns": {},
            "confidence_trends": [],
            "intent_distribution": {},
            "cache_performance": {"hits": 0, "misses": 0},
            "user_activity": {}
        })
        
        # Normalize query for pattern analysis
        normalized_query = query.lower().strip()
        
        # Extract document sources
        document_sources = [s.get("source", "unknown") for s in sources if s.get("source")]
        
        # Record query entry
        query_entry = {
            "query": query,
            "normalized_query": normalized_query,
            "response_time": response_time,
            "sources_count": len(sources),
            "document_sources": document_sources,
            "intent": intent or "unknown",
            "confidence": confidence,
            "verification_status": verification_status or "not_verified",
            "cache_hit": cache_hit,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat()
        }
        
        analytics["queries"].append(query_entry)
        
        # Track document usage
        for doc in document_sources:
            if doc != "unknown":
                if doc not in analytics["document_usage"]:
                    analytics["document_usage"][doc] = {
                        "query_count": 0,
                        "total_relevance": 0.0,
                        "last_accessed": None
                    }
                analytics["document_usage"][doc]["query_count"] += 1
                analytics["document_usage"][doc]["last_accessed"] = datetime.now().isoformat()
        
        # Track query patterns (normalized queries)
        if normalized_query not in analytics["query_patterns"]:
            analytics["query_patterns"][normalized_query] = {
                "count": 0,
                "avg_response_time": 0.0,
                "total_response_time": 0.0,
                "first_seen": datetime.now().isoformat(),
                "last_seen": datetime.now().isoformat()
            }
        
        pattern = analytics["query_patterns"][normalized_query]
        pattern["count"] += 1
        pattern["total_response_time"] += response_time
        pattern["avg_response_time"] = pattern["total_response_time"] / pattern["count"]
        pattern["last_seen"] = datetime.now().isoformat()
        
        # Track confidence trends
        if confidence is not None:
            analytics["confidence_trends"].append({
                "confidence": confidence,
                "timestamp": datetime.now().isoformat(),
                "query": query[:100]  # Store first 100 chars
            })
        
        # Track intent distribution
        intent_type = intent or "unknown"
        if intent_type not in analytics["intent_distribution"]:
            analytics["intent_distribution"][intent_type] = 0
        analytics["intent_distribution"][intent_type] += 1
        
        # Track cache performance
        if cache_hit:
            analytics["cache_performance"]["hits"] += 1
        else:
            analytics["cache_performance"]["misses"] += 1
        
        # Track user activity
        if user_id:
            if user_id not in analytics["user_activity"]:
                analytics["user_activity"][user_id] = {
                    "query_count": 0,
                    "last_activity": None
                }
            analytics["user_activity"][user_id]["query_count"] += 1
            analytics["user_activity"][user_id]["last_activity"] = datetime.now().isoformat()
        
        # Keep only last 5000 queries to avoid file bloat
        if len(analytics["queries"]) > 5000:
            analytics["queries"] = analytics["queries"][-5000:]
        
        # Keep only last 1000 confidence trends
        if len(analytics["confidence_trends"]) > 1000:
            analytics["confidence_trends"] = analytics["confidence_trends"][-1000:]
        
        save_json_file(ANALYTICS_FILE, analytics)
    
    @staticmethod
    def get_query_analytics(hours: int = 24) -> Dict:
        """Get comprehensive query analytics."""
        analytics = load_json_file(ANALYTICS_FILE, {
            "queries": [],
            "document_usage": {},
            "query_patterns": {},
            "confidence_trends": [],
            "intent_distribution": {},
            "cache_performance": {"hits": 0, "misses": 0},
            "user_activity": {}
        })
        
        # Filter by time
        cutoff = datetime.now() - timedelta(hours=hours)
        recent_queries = [
            q for q in analytics.get("queries", [])
            if datetime.fromisoformat(q.get("timestamp", "")) >= cutoff
        ]
        
        if not recent_queries:
            return {
                "period_hours": hours,
                "total_queries": 0,
                "most_asked_queries": [],
                "document_usage": [],
                "intent_distribution": {},
                "confidence_stats": {},
                "cache_performance": {},
                "query_trends": []
            }
        
        # Most asked queries
        query_counts = Counter([q["normalized_query"] for q in recent_queries])
        most_asked = [
            {
                "query": query,
                "count": count,
                "pattern_data": analytics["query_patterns"].get(query, {})
            }
            for query, count in query_counts.most_common(10)
        ]
        
        # Document usage (top documents)
        doc_usage = analytics.get("document_usage", {})
        doc_usage_sorted = sorted(
            doc_usage.items(),
            key=lambda x: x[1].get("query_count", 0),
            reverse=True
        )[:10]
        
        document_usage = [
            {
                "document": doc,
                "query_count": data.get("query_count", 0),
                "last_accessed": data.get("last_accessed")
            }
            for doc, data in doc_usage_sorted
        ]
        
        # Intent distribution
        intent_dist = analytics.get("intent_distribution", {})
        
        # Confidence statistics
        confidences = [q.get("confidence") for q in recent_queries if q.get("confidence") is not None]
        confidence_stats = {}
        if confidences:
            confidence_stats = {
                "avg": round(sum(confidences) / len(confidences), 3),
                "min": round(min(confidences), 3),
                "max": round(max(confidences), 3),
                "high_confidence_count": sum(1 for c in confidences if c >= 0.7),
                "low_confidence_count": sum(1 for c in confidences if c < 0.5),
                "total_with_confidence": len(confidences)
            }
        
        # Cache performance
        cache_perf = analytics.get("cache_performance", {"hits": 0, "misses": 0})
        total_cache_requests = cache_perf["hits"] + cache_perf["misses"]
        cache_performance = {
            "hits": cache_perf["hits"],
            "misses": cache_perf["misses"],
            "hit_rate": round(cache_perf["hits"] / total_cache_requests * 100, 2) if total_cache_requests > 0 else 0
        }
        
        # Query trends (hourly breakdown)
        hourly_queries = defaultdict(int)
        for q in recent_queries:
            timestamp = datetime.fromisoformat(q["timestamp"])
            hour_key = timestamp.strftime("%Y-%m-%d %H:00")
            hourly_queries[hour_key] += 1
        
        query_trends = [
            {"hour": hour, "count": count}
            for hour, count in sorted(hourly_queries.items())
        ]
        
        # Response time by intent
        response_times_by_intent = defaultdict(list)
        for q in recent_queries:
            intent = q.get("intent", "unknown")
            response_times_by_intent[intent].append(q.get("response_time", 0))
        
        intent_performance = {
            intent: {
                "avg_response_time": round(sum(times) / len(times), 3) if times else 0,
                "query_count": len(times)
            }
            for intent, times in response_times_by_intent.items()
        }
        
        return {
            "period_hours": hours,
            "total_queries": len(recent_queries),
            "most_asked_queries": most_asked,
            "document_usage": document_usage,
            "intent_distribution": intent_dist,
            "intent_performance": intent_performance,
            "confidence_stats": confidence_stats,
            "cache_performance": cache_performance,
            "query_trends": query_trends,
            "verification_stats": AnalyticsTracker._get_verification_stats(recent_queries)
        }
    
    @staticmethod
    def _get_verification_stats(queries: List[Dict]) -> Dict:
        """Get answer verification statistics."""
        verification_statuses = [q.get("verification_status", "not_verified") for q in queries]
        status_counts = Counter(verification_statuses)
        
        total_verified = sum(
            count for status, count in status_counts.items()
            if status != "not_verified"
        )
        
        return {
            "total_verified": total_verified,
            "supported_count": status_counts.get("supported", 0),
            "partial_count": status_counts.get("partial", 0),
            "unsupported_count": status_counts.get("unsupported", 0),
            "not_verified_count": status_counts.get("not_verified", 0),
            "by_status": dict(status_counts)
        }
    
    @staticmethod
    def get_knowledge_gaps(processor, hours: int = 24) -> List[Dict]:
        """Identify potential knowledge gaps based on low confidence queries."""
        analytics = load_json_file(ANALYTICS_FILE, {"queries": []})
        
        cutoff = datetime.now() - timedelta(hours=hours)
        recent_queries = [
            q for q in analytics.get("queries", [])
            if datetime.fromisoformat(q.get("timestamp", "")) >= cutoff
        ]
        
        # Find queries with low confidence or no sources
        low_confidence_queries = [
            q for q in recent_queries
            if (q.get("confidence", 1.0) < 0.5) or (q.get("sources_count", 0) == 0)
        ]
        
        # Group by intent and find patterns
        gaps = []
        intent_groups = defaultdict(list)
        for q in low_confidence_queries:
            intent = q.get("intent", "unknown")
            intent_groups[intent].append(q)
        
        for intent, queries in intent_groups.items():
            if len(queries) >= 3:  # At least 3 queries with issues
                gaps.append({
                    "intent": intent,
                    "query_count": len(queries),
                    "avg_confidence": round(
                        sum(q.get("confidence", 0) for q in queries) / len(queries), 3
                    ) if queries else 0,
                    "sample_queries": [q["query"][:100] for q in queries[:5]],
                    "recommendation": f"Consider adding more content related to {intent} queries"
                })
        
        return gaps
    
    @staticmethod
    def get_user_insights(hours: int = 24) -> Dict:
        """Get user behavior insights."""
        analytics = load_json_file(ANALYTICS_FILE, {
            "user_activity": {},
            "queries": []
        })
        
        cutoff = datetime.now() - timedelta(hours=hours)
        recent_queries = [
            q for q in analytics.get("queries", [])
            if datetime.fromisoformat(q.get("timestamp", "")) >= cutoff
            and q.get("user_id")
        ]
        
        # Active users
        user_activity = analytics.get("user_activity", {})
        active_users = [
            {
                "user_id": user_id,
                "query_count": data.get("query_count", 0),
                "last_activity": data.get("last_activity")
            }
            for user_id, data in user_activity.items()
            if data.get("last_activity") and datetime.fromisoformat(data["last_activity"]) >= cutoff
        ]
        
        active_users.sort(key=lambda x: x["query_count"], reverse=True)
        
        return {
            "total_active_users": len(active_users),
            "top_users": active_users[:10],
            "total_user_queries": len(recent_queries)
        }

