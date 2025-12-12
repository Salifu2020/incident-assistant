"""
Knowledge base health monitoring and metrics tracking.
"""
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import threading

# Get project root directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEALTH_FILE = os.path.join(PROJECT_ROOT, "data", "health_metrics.json")

# Thread lock for file operations
_file_lock = threading.Lock()


def ensure_data_dir():
    """Ensure data directory exists."""
    data_dir = os.path.dirname(HEALTH_FILE)
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


class HealthMonitor:
    """Monitor knowledge base health and track metrics."""
    
    @staticmethod
    def record_metric(metric_type: str, value: float, metadata: Dict = None):
        """Record a health metric."""
        metrics = load_json_file(HEALTH_FILE, {"metrics": [], "summary": {}})
        
        metric = {
            "type": metric_type,
            "value": value,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        metrics["metrics"].append(metric)
        
        # Keep only last 1000 metrics
        if len(metrics["metrics"]) > 1000:
            metrics["metrics"] = metrics["metrics"][-1000:]
        
        save_json_file(HEALTH_FILE, metrics)
    
    @staticmethod
    def record_document_processed(filename: str, chunk_count: int, file_size: int, success: bool = True):
        """Record document processing event."""
        HealthMonitor.record_metric(
            "document_processed",
            1.0 if success else 0.0,
            {
                "filename": filename,
                "chunk_count": chunk_count,
                "file_size": file_size,
                "success": success
            }
        )
    
    @staticmethod
    def record_query(query: str, response_time: float, sources_count: int, success: bool = True):
        """Record query execution."""
        HealthMonitor.record_metric(
            "query_executed",
            response_time,
            {
                "query_length": len(query),
                "sources_count": sources_count,
                "success": success
            }
        )
    
    @staticmethod
    def record_error(error_type: str, error_message: str, context: Dict = None):
        """Record an error."""
        HealthMonitor.record_metric(
            "error",
            1.0,
            {
                "error_type": error_type,
                "error_message": error_message,
                "context": context or {}
            }
        )
    
    @staticmethod
    def get_health_summary(processor) -> Dict:
        """Get comprehensive health summary."""
        try:
            collection_count = processor.collection.count()
            
            # Get document list
            documents = []
            try:
                docs_data = processor.list_documents()
                documents = docs_data.get("documents", [])
            except:
                pass
            
            # Calculate metrics
            total_docs = len(documents)
            total_chunks = collection_count
            avg_chunks_per_doc = round(total_chunks / total_docs, 2) if total_docs > 0 else 0
            
            # File type distribution
            file_types = {}
            total_size = 0
            for doc in documents:
                file_type = doc.get("file_type", "unknown")
                file_types[file_type] = file_types.get(file_type, 0) + 1
                total_size += doc.get("file_size", 0)
            
            # Load historical metrics
            metrics_data = load_json_file(HEALTH_FILE, {"metrics": [], "summary": {}})
            all_metrics = metrics_data.get("metrics", [])
            
            # Calculate time-based metrics (last 24 hours)
            now = datetime.now()
            last_24h = now - timedelta(hours=24)
            recent_metrics = [
                m for m in all_metrics
                if datetime.fromisoformat(m.get("timestamp", "")) >= last_24h
            ]
            
            # Query metrics
            query_metrics = [m for m in recent_metrics if m.get("type") == "query_executed"]
            query_count_24h = len(query_metrics)
            avg_response_time = (
                sum(m.get("value", 0) for m in query_metrics) / query_count_24h
                if query_count_24h > 0 else 0
            )
            
            # Error metrics
            error_metrics = [m for m in recent_metrics if m.get("type") == "error"]
            error_count_24h = len(error_metrics)
            error_rate = (error_count_24h / query_count_24h * 100) if query_count_24h > 0 else 0
            
            # Document processing metrics
            doc_metrics = [m for m in recent_metrics if m.get("type") == "document_processed"]
            docs_processed_24h = len(doc_metrics)
            successful_docs = sum(1 for m in doc_metrics if m.get("metadata", {}).get("success", False))
            success_rate = (successful_docs / docs_processed_24h * 100) if docs_processed_24h > 0 else 100
            
            # Last update
            last_update = None
            if documents:
                dates = [doc.get("upload_date") for doc in documents if doc.get("upload_date")]
                if dates:
                    last_update = max(dates)
            
            # Health score calculation (0-100)
            health_score = 100
            if total_chunks == 0:
                health_score -= 30  # Empty KB
            if error_rate > 10:
                health_score -= 20  # High error rate
            elif error_rate > 5:
                health_score -= 10
            if avg_response_time > 5:
                health_score -= 10  # Slow responses
            if success_rate < 80:
                health_score -= 15  # Low processing success rate
            
            health_score = max(0, min(100, health_score))
            
            # Determine health status
            if health_score >= 90:
                status = "excellent"
            elif health_score >= 75:
                status = "good"
            elif health_score >= 60:
                status = "fair"
            elif health_score >= 40:
                status = "poor"
            else:
                status = "critical"
            
            return {
                "status": status,
                "health_score": health_score,
                "timestamp": datetime.now().isoformat(),
                "knowledge_base": {
                    "total_documents": total_docs,
                    "total_chunks": total_chunks,
                    "avg_chunks_per_doc": avg_chunks_per_doc,
                    "total_size_bytes": total_size,
                    "total_size_mb": round(total_size / (1024 * 1024), 2),
                    "file_type_distribution": file_types,
                    "last_update": last_update
                },
                "performance": {
                    "queries_24h": query_count_24h,
                    "avg_response_time_sec": round(avg_response_time, 3),
                    "error_count_24h": error_count_24h,
                    "error_rate_percent": round(error_rate, 2),
                    "docs_processed_24h": docs_processed_24h,
                    "processing_success_rate": round(success_rate, 2)
                },
                "alerts": HealthMonitor._generate_alerts(
                    total_chunks, error_rate, avg_response_time, success_rate, health_score
                )
            }
        except Exception as e:
            return {
                "status": "error",
                "health_score": 0,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    @staticmethod
    def _generate_alerts(chunks: int, error_rate: float, response_time: float, success_rate: float, health_score: int) -> List[Dict]:
        """Generate health alerts."""
        alerts = []
        
        if chunks == 0:
            alerts.append({
                "level": "warning",
                "type": "empty_knowledge_base",
                "message": "Knowledge base is empty. Upload documents to get started.",
                "severity": "high"
            })
        
        if error_rate > 10:
            alerts.append({
                "level": "error",
                "type": "high_error_rate",
                "message": f"High error rate: {error_rate:.1f}% of queries are failing.",
                "severity": "critical"
            })
        elif error_rate > 5:
            alerts.append({
                "level": "warning",
                "type": "elevated_error_rate",
                "message": f"Elevated error rate: {error_rate:.1f}% of queries are failing.",
                "severity": "medium"
            })
        
        if response_time > 5:
            alerts.append({
                "level": "warning",
                "type": "slow_responses",
                "message": f"Slow response times: Average {response_time:.1f}s per query.",
                "severity": "medium"
            })
        
        if success_rate < 80:
            alerts.append({
                "level": "warning",
                "type": "low_processing_success",
                "message": f"Low document processing success rate: {success_rate:.1f}%.",
                "severity": "medium"
            })
        
        if health_score < 40:
            alerts.append({
                "level": "error",
                "type": "critical_health",
                "message": "Knowledge base health is critical. Immediate attention required.",
                "severity": "critical"
            })
        
        return alerts
    
    @staticmethod
    def get_metrics_history(metric_type: Optional[str] = None, hours: int = 24, limit: int = 100) -> List[Dict]:
        """Get historical metrics."""
        metrics_data = load_json_file(HEALTH_FILE, {"metrics": []})
        all_metrics = metrics_data.get("metrics", [])
        
        # Filter by time
        cutoff = datetime.now() - timedelta(hours=hours)
        filtered = [
            m for m in all_metrics
            if datetime.fromisoformat(m.get("timestamp", "")) >= cutoff
        ]
        
        # Filter by type if specified
        if metric_type:
            filtered = [m for m in filtered if m.get("type") == metric_type]
        
        # Sort by timestamp (newest first) and limit
        filtered.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return filtered[:limit]
    
    @staticmethod
    def get_performance_stats(hours: int = 24) -> Dict:
        """Get performance statistics."""
        metrics = HealthMonitor.get_metrics_history(hours=hours)
        
        query_metrics = [m for m in metrics if m.get("type") == "query_executed"]
        error_metrics = [m for m in metrics if m.get("type") == "error"]
        doc_metrics = [m for m in metrics if m.get("type") == "document_processed"]
        
        return {
            "total_queries": len(query_metrics),
            "total_errors": len(error_metrics),
            "total_documents_processed": len(doc_metrics),
            "avg_query_time": (
                sum(m.get("value", 0) for m in query_metrics) / len(query_metrics)
                if query_metrics else 0
            ),
            "error_rate": (
                len(error_metrics) / len(query_metrics) * 100
                if query_metrics else 0
            ),
            "successful_documents": sum(
                1 for m in doc_metrics
                if m.get("metadata", {}).get("success", False)
            )
        }


