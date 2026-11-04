from .ingestion import DocumentProcessor
from .llm_providers import get_llm_provider, LLMProvider
import re
import os
import json
import hashlib
import time
from collections import Counter
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# Windows console encoding can crash on emoji-containing print() output
# (e.g. 'UnicodeEncodeError: charmap' on cp1252). Make print() safe in this module.
_real_print = print
def _to_ascii_safe(v) -> str:
    try:
        s = str(v)
    except Exception:
        s = repr(v)
    # Force ASCII-safe rendering so stdout encoding never throws.
    return s.encode("utf-8", errors="backslashreplace").decode("ascii", errors="backslashreplace")

def _safe_print(*args, **kwargs):
    try:
        return _real_print(*args, **kwargs)
    except UnicodeEncodeError:
        safe_args = [_to_ascii_safe(a) for a in args]
        return _real_print(*safe_args, **kwargs)

print = _safe_print

# Keep ollama import for backward compatibility (will be used if LLM provider fallback is needed)
try:
    import ollama
    _ollama_available = True
except ImportError:
    _ollama_available = False


class QueryCache:
    """Smart query caching system for improved performance."""
    
    def __init__(self, default_ttl: int = 3600, max_size: int = 1000):
        """
        Initialize query cache.
        
        Args:
            default_ttl: Default time-to-live in seconds (default: 1 hour)
            max_size: Maximum number of cached entries (default: 1000)
        """
        self.cache: Dict[str, Dict] = {}
        self.default_ttl = default_ttl
        self.max_size = max_size
        self.hit_count = 0
        self.miss_count = 0
        self.invalidation_count = 0
        self._last_invalidation = None
        
    def _generate_cache_key(self, query: str, document_filters: List = None, 
                           advanced_filters: Dict = None, language: str = None) -> str:
        """Generate a unique cache key for a query."""
        # Normalize query (lowercase, strip whitespace)
        normalized_query = query.lower().strip()
        
        # Create key components
        key_parts = [normalized_query]
        
        # Add document filters if present
        if document_filters:
            key_parts.append("docs:" + ",".join(sorted(document_filters)))
        
        # Add advanced filters if present
        if advanced_filters:
            filter_str = json.dumps(advanced_filters, sort_keys=True)
            key_parts.append("filters:" + filter_str)
        
        # Add language if present
        if language:
            key_parts.append("lang:" + language)
        
        # Create hash of combined key
        key_string = "|".join(key_parts)
        return hashlib.sha256(key_string.encode('utf-8')).hexdigest()
    
    def get(self, cache_key: str) -> Optional[Dict]:
        """
        Get cached result if available and not expired.
        
        Args:
            cache_key: The cache key to look up
            
        Returns:
            Cached result dict with 'answer', 'sources', 'intent_info', 'confidence_info', 'verification_info'
            or None if not found or expired
        """
        if cache_key not in self.cache:
            self.miss_count += 1
            return None
        
        entry = self.cache[cache_key]
        
        # Check if expired
        if time.time() > entry['expires_at']:
            # Remove expired entry
            del self.cache[cache_key]
            self.miss_count += 1
            return None
        
        # Cache hit!
        self.hit_count += 1
        entry['access_count'] = entry.get('access_count', 0) + 1
        entry['last_accessed'] = time.time()
        
        return {
            'answer': entry['answer'],
            'sources': entry['sources'],
            'intent_info': entry.get('intent_info', {}),
            'confidence_info': entry.get('confidence_info'),
            'verification_info': entry.get('verification_info')
        }
    
    def set(self, cache_key: str, answer: str, sources: List, 
            intent_info: Dict = None, confidence_info: Dict = None, 
            verification_info: Dict = None, ttl: int = None):
        """
        Store result in cache.
        
        Args:
            cache_key: The cache key
            answer: The answer text
            sources: List of source documents
            intent_info: Intent classification info
            confidence_info: Confidence scoring info
            verification_info: Answer verification info
            ttl: Time-to-live in seconds (uses default if None)
        """
        # Enforce max size - remove oldest entries if needed
        if len(self.cache) >= self.max_size:
            # Remove least recently used entries (20% of cache)
            entries_to_remove = max(1, self.max_size // 5)
            sorted_entries = sorted(
                self.cache.items(),
                key=lambda x: x[1].get('last_accessed', x[1]['created_at'])
            )
            for key, _ in sorted_entries[:entries_to_remove]:
                del self.cache[key]
        
        # Store entry
        expires_at = time.time() + (ttl or self.default_ttl)
        self.cache[cache_key] = {
            'answer': answer,
            'sources': sources,
            'intent_info': intent_info or {},
            'confidence_info': confidence_info,
            'verification_info': verification_info,
            'created_at': time.time(),
            'expires_at': expires_at,
            'last_accessed': time.time(),
            'access_count': 1
        }
    
    def invalidate(self, pattern: str = None):
        """
        Invalidate cache entries.
        
        Args:
            pattern: Optional pattern to match (if None, clears all)
        """
        if pattern is None:
            # Clear all cache
            cleared_count = len(self.cache)
            self.cache.clear()
            self.invalidation_count += 1
            self._last_invalidation = time.time()
            return cleared_count
        
        # Pattern-based invalidation (e.g., by document name)
        keys_to_remove = []
        for key, entry in self.cache.items():
            # Check if any source matches the pattern
            sources = entry.get('sources', [])
            for source in sources:
                if pattern in str(source.get('source', '')):
                    keys_to_remove.append(key)
                    break
        
        for key in keys_to_remove:
            del self.cache[key]
        
        if keys_to_remove:
            self.invalidation_count += 1
            self._last_invalidation = time.time()
        
        return len(keys_to_remove)
    
    def clear_expired(self):
        """Remove all expired entries from cache."""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self.cache.items()
            if current_time > entry['expires_at']
        ]
        for key in expired_keys:
            del self.cache[key]
        return len(expired_keys)
    
    def get_stats(self) -> Dict:
        """Get cache statistics."""
        self.clear_expired()  # Clean up expired entries first
        
        total_requests = self.hit_count + self.miss_count
        hit_rate = (self.hit_count / total_requests * 100) if total_requests > 0 else 0
        
        # Calculate average access count for cached entries
        avg_access_count = 0
        if self.cache:
            avg_access_count = sum(
                entry.get('access_count', 0) for entry in self.cache.values()
            ) / len(self.cache)
        
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hits': self.hit_count,
            'misses': self.miss_count,
            'hit_rate': round(hit_rate, 2),
            'invalidations': self.invalidation_count,
            'last_invalidation': self._last_invalidation,
            'avg_access_count': round(avg_access_count, 2),
            'total_requests': total_requests
        }
    
    def clear(self):
        """Clear all cache entries."""
        cleared_count = len(self.cache)
        self.cache.clear()
        self.invalidation_count += 1
        self._last_invalidation = time.time()
        return cleared_count


class KnowledgeAssistant:
    def __init__(self, processor, model_name: str = "mistral", max_context_chars=2500, enable_streaming=True, enable_query_expansion=True, enable_hybrid_search=True, enable_reranking=True, enable_intent_classification=True, enable_multi_step_reasoning=True, enable_learning_from_feedback=True, enable_context_summarization=True, summarization_threshold=1.2, enable_confidence_scoring=True, enable_answer_verification=True, enable_query_caching=True, cache_ttl=3600, cache_max_size=1000):
        self.processor = processor
        self.llm_model = model_name
        self.max_context_chars = max_context_chars
        self.enable_streaming = enable_streaming
        self.enable_query_expansion = enable_query_expansion
        self.enable_hybrid_search = enable_hybrid_search
        self.enable_reranking = enable_reranking
        self.enable_intent_classification = enable_intent_classification
        self.enable_multi_step_reasoning = enable_multi_step_reasoning
        self.enable_learning_from_feedback = enable_learning_from_feedback
        self.enable_context_summarization = enable_context_summarization
        self.summarization_threshold = summarization_threshold  # Summarize if context exceeds max_context_chars * threshold
        self.enable_confidence_scoring = enable_confidence_scoring
        self.enable_answer_verification = enable_answer_verification  # Enable answer verification to prevent hallucinations
        self.enable_query_caching = enable_query_caching  # Enable smart query caching
        
        # Initialize LLM provider (Groq > OpenAI > Ollama)
        try:
            self._llm_provider = get_llm_provider(model=model_name)
            print(f"✅ LLM provider initialized: {type(self._llm_provider).__name__}")
        except Exception as e:
            print(f"⚠️ LLM provider initialization failed: {e}")
            self._llm_provider = None
        
        # Initialize query cache
        if self.enable_query_caching:
            self.query_cache = QueryCache(default_ttl=cache_ttl, max_size=cache_max_size)
            print(f"✅ Query caching enabled (TTL: {cache_ttl}s, Max size: {cache_max_size})")
        else:
            self.query_cache = None
        
        # Initialize learning data storage
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.learning_data_file = os.path.join(project_root, "data", "learning_patterns.json")
        
        # Cache for document-based query suggestions
        self._document_suggestions_cache = None
        self._document_suggestions_cache_time = None
        self._document_suggestions_cache_ttl = 3600  # Cache for 1 hour
        
        # Multi-language support
        self.enable_multilanguage = True  # Enable multi-language support
        self.default_language = "en"  # Default language (English)
        self.supported_languages = ["en", "es", "fr", "de", "it", "pt", "zh", "ja", "ko", "ar", "ru", "hi"]
        self._translation_cache = {}  # Cache for translations

        # Style control: phrases we never want at beginning/end of answers
        self._answer_style_prefixes = [
            "as mentioned in your context",
            "as mentioned in the context",
            "as mentioned in the provided context",
            "as noted in your context",
            "as noted in the context",
            "as stated in your context",
            "as stated in the context",
            "according to the context",
            "based on the context",
            "from the context",
            "according to the provided",
            "based on the provided",
            "as per the context",
            "per the context",
            "as per the provided context",
        ]
        
        self._load_learning_data()
        
        self.reset_history()

    def _should_fallback_to_ollama(self, error: Exception) -> bool:
        """Only fall back to Ollama for transient failures, not auth/config errors."""
        provider_pref = (os.environ.get("LLM_PROVIDER") or "auto").strip().lower()
        if provider_pref in {"groq", "openai"}:
            return False
        err = str(error).lower()
        auth_markers = (
            "invalid api key",
            "expired_api_key",
            "incorrect api key",
            "unauthorized",
            "authentication",
            "401",
            "403",
        )
        return not any(marker in err for marker in auth_markers)

    def _llm_chat(self, messages: list, stream: bool = False, 
                  temperature: float = 0.3, max_tokens: int = 500) -> str:
        """
        Unified LLM chat method that uses the configured provider.
        Falls back to direct Ollama only when that is a sensible recovery path.
        """
        provider_error = None
        # Try the configured LLM provider first
        if self._llm_provider is not None:
            try:
                return self._llm_provider.chat(
                    messages=messages,
                    stream=stream,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            except Exception as e:
                provider_error = e
                if not self._should_fallback_to_ollama(e):
                    raise RuntimeError(
                        f"LLM provider failed: {e}. "
                        "Check GROQ_API_KEY / OPENAI_API_KEY in .env.local and restart the API."
                    ) from e
                print(f"⚠️ LLM provider error: {e}, falling back to Ollama")
        
        # Fallback to direct Ollama
        if _ollama_available:
            try:
                if stream:
                    response_text = ""
                    stream_resp = ollama.chat(
                        model=self.llm_model,
                        messages=messages,
                        stream=True,
                        options={"temperature": temperature, "num_predict": max_tokens}
                    )
                    for chunk in stream_resp:
                        if 'message' in chunk and 'content' in chunk['message']:
                            response_text += chunk['message']['content']
                    return response_text.strip()
                response = ollama.chat(
                    model=self.llm_model,
                    messages=messages,
                    stream=False,
                    options={"temperature": temperature, "num_predict": max_tokens}
                )
                return response["message"]["content"].strip()
            except Exception as ollama_error:
                if provider_error is not None:
                    raise RuntimeError(
                        f"LLM provider failed ({provider_error}); Ollama fallback also failed ({ollama_error})."
                    ) from ollama_error
                raise
        
        if provider_error is not None:
            raise RuntimeError(
                f"LLM provider failed: {provider_error}. "
                "No Ollama fallback available. Set a valid GROQ_API_KEY or start Ollama."
            ) from provider_error
        raise RuntimeError("No LLM provider available. Set GROQ_API_KEY, OPENAI_API_KEY, or ensure Ollama is running.")

    def _llm_chat_stream(self, messages: list, 
                         temperature: float = 0.3, max_tokens: int = 500):
        """
        Stream LLM response. Yields chunks of text.
        """
        provider_error = None
        # Try the configured LLM provider first
        if self._llm_provider is not None:
            try:
                for chunk in self._llm_provider.chat_stream(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                ):
                    yield chunk
                return
            except Exception as e:
                provider_error = e
                if not self._should_fallback_to_ollama(e):
                    raise RuntimeError(
                        f"LLM provider failed: {e}. "
                        "Check GROQ_API_KEY / OPENAI_API_KEY in .env.local and restart the API."
                    ) from e
                print(f"⚠️ LLM provider stream error: {e}, falling back to Ollama")
        
        # Fallback to direct Ollama
        if _ollama_available:
            try:
                stream = ollama.chat(
                    model=self.llm_model,
                    messages=messages,
                    stream=True,
                    options={"temperature": temperature, "num_predict": max_tokens}
                )
                for chunk in stream:
                    if 'message' in chunk and 'content' in chunk['message']:
                        yield chunk['message']['content']
                return
            except Exception as ollama_error:
                if provider_error is not None:
                    raise RuntimeError(
                        f"LLM provider failed ({provider_error}); Ollama fallback also failed ({ollama_error})."
                    ) from ollama_error
                raise
        
        if provider_error is not None:
            raise RuntimeError(
                f"LLM provider failed: {provider_error}. "
                "No Ollama fallback available. Set a valid GROQ_API_KEY or start Ollama."
            ) from provider_error
        raise RuntimeError("No LLM provider available for streaming.")

    def _clean_answer_style(self, answer: str) -> str:
        """
        Remove context-referencing boilerplate from the beginning/end of the answer.
        User requirement: do not include these phrases at the beginning or end.
        Also removes any HTML tags that the LLM might generate.
        """
        if not answer:
            return answer

        text = answer.strip()
        
        # Strip HTML tags (LLM should not return HTML, but sometimes does)
        import re
        text = re.sub(r'<[^>]+>', '', text)  # Remove all HTML tags
        text = re.sub(r'&nbsp;', ' ', text)  # Replace HTML entities
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)
        text = re.sub(r'&quot;', '"', text)
        text = text.strip()

        # Fast path: simple prefix list
        lower = text.lower().strip()
        for p in self._answer_style_prefixes:
            if lower.startswith(p):
                text = text[len(p):].lstrip(" \t:;,-.\n\r")
                break

        # Regex for more variants (case/punctuation/spacing)
        leading_re = re.compile(
            r"^\s*(as\s+(mentioned|noted|stated)\s+in\s+(your|the|this)\s+context|"
            r"according\s+to\s+(the|this)\s+context|based\s+on\s+(the|this)\s+context|from\s+(the|this)\s+context)"
            r"\s*[:;,\-–—\.]*\s*",
            re.IGNORECASE,
        )
        text = leading_re.sub("", text).lstrip()

        trailing_re = re.compile(
            r"\s*[,;:\-–—\.]*\s*(as\s+(mentioned|noted|stated)\s+in\s+(your|the|this)\s+context|"
            r"as\s+(mentioned|noted|stated)\s+above|as\s+described\s+above)\s*\.?\s*$",
            re.IGNORECASE,
        )
        text = trailing_re.sub("", text).rstrip()

        return text.strip()

    

    def reset_history(self):
        self.chat_history = [
            {
                "role": "system",
                "content": (
                    "You are a helpful, knowledgeable assistant. Answer questions concisely and accurately "
                    "using only the information provided in the context.\n\n"
                    "Guidelines:\n"
                    "- Answer directly and confidently, as if you know the information\n"
                    "- Be specific and cite relevant details from the context\n"
                    "- If the context doesn't contain the answer, say so briefly\n"
                    "- Never make up information or use knowledge outside the context\n"
                    "- Keep answers concise but complete\n"
                    "- When answering follow-up questions, use the conversation history to understand context\n"
                    "- If a question refers to something mentioned earlier (like 'it', 'that', 'this', 'they'), "
                    "use the previous conversation to understand what is being referenced\n"
                    "- Maintain consistency with previous answers in the conversation"
                )
            }
        ]

    def retrieve_context(self, query, k=8, document_filters=None, advanced_filters=None):
        """Retrieve context from the knowledge base with source information.
        
        Args:
            query: The search query
            k: Number of results to retrieve
            document_filters: Optional list of document filenames to filter by (legacy)
            advanced_filters: Optional AdvancedSearchFilters object for advanced filtering
        """
        try:
            # Quick check if collection exists and has data (with caching)
            try:
                # Cache collection count for 5 seconds to avoid repeated queries
                if not hasattr(self, '_collection_count_cache'):
                    self._collection_count_cache = {'count': None, 'timestamp': 0}
                
                current_time = time.time()
                if (self._collection_count_cache['count'] is None or 
                    current_time - self._collection_count_cache['timestamp'] > 5):
                    self._collection_count_cache['count'] = self.processor.collection.count()
                    self._collection_count_cache['timestamp'] = current_time
                
                collection_count = self._collection_count_cache['count']
                if collection_count == 0:
                    return "", []
            except Exception:
                return "", []
            
            # Adaptive k: fetch enough chunks for document summaries; favor recall over speed
            n_results = min(k, max(6, collection_count // 5)) if collection_count else k
            
            # Update max_results if specified in advanced_filters
            if advanced_filters and advanced_filters.max_results:
                n_results = min(advanced_filters.max_results, n_results)
            
            # Expand query for better retrieval
            expanded_queries = self.expand_query(query)
            if len(expanded_queries) > 1:
                print(f"🔍 Query expansion: {len(expanded_queries)} variations generated")
            
            # If we have multiple query variations, retrieve for each and merge results
            all_docs = []
            all_distances = []
            all_metadatas = []
            
            if len(expanded_queries) > 1:
                # Batch retrieve with all query variations at once (optimized)
                results_per_query = max(2, n_results // len(expanded_queries))
                
                # Build where conditions once
                where_conditions = self._build_where_conditions(document_filters, advanced_filters)
                
                # Batch query: query all variations in one call for better performance
                try:
                    query_params = {
                        "query_texts": expanded_queries,  # Batch all queries
                        "n_results": results_per_query,
                        "include": ['documents', 'distances', 'metadatas']
                    }
                    
                    if where_conditions:
                        query_params["where"] = where_conditions
                    
                    # Single batch query instead of multiple individual queries
                    batch_result = self.processor.collection.query(**query_params)
                    
                    # Process batch results
                    if batch_result.get('documents'):
                        for query_idx, docs in enumerate(batch_result['documents']):
                            if docs:
                                all_docs.extend(docs)
                                if batch_result.get('distances') and batch_result['distances'][query_idx]:
                                    all_distances.extend(batch_result['distances'][query_idx])
                                if batch_result.get('metadatas') and batch_result['metadatas'][query_idx]:
                                    all_metadatas.extend(batch_result['metadatas'][query_idx])
                except Exception as e:
                    print(f"⚠️ Batch query failed: {e}, falling back to individual queries")
                    # Fallback to individual queries
                    for expanded_query in expanded_queries:
                        try:
                            query_params = {
                                "query_texts": [expanded_query],
                                "n_results": results_per_query,
                                "include": ['documents', 'distances', 'metadatas']
                            }
                            
                            if where_conditions:
                                query_params["where"] = where_conditions
                            
                            result = self.processor.collection.query(**query_params)
                            
                            if result.get('documents') and result['documents'][0]:
                                all_docs.extend(result['documents'][0])
                                all_distances.extend(result.get('distances', [[]])[0])
                                all_metadatas.extend(result.get('metadatas', [[]])[0])
                        except Exception as e2:
                            print(f"⚠️ Error retrieving with expanded query '{expanded_query}': {e2}")
                            continue
                
                # If hybrid search is enabled, also do keyword search and merge
                if self.enable_hybrid_search and all_docs:
                    try:
                        keyword_docs, keyword_distances, keyword_metadatas = self._keyword_search(
                            query,
                            k=n_results * 2,
                            document_filters=document_filters,
                            advanced_filters=advanced_filters
                        )
                        
                        # Merge semantic (from expanded queries) and keyword results
                        docs, distances, metadatas = self._merge_search_results(
                            all_docs, all_distances, all_metadatas,
                            keyword_docs, keyword_distances, keyword_metadatas,
                            n_results
                        )
                    except Exception as e:
                        print(f"⚠️ Hybrid search merge failed: {e}, using semantic results only")
                        # Fallback to semantic results only
                        combined = list(zip(all_docs, all_distances, all_metadatas))
                        seen_texts = set()
                        unique_results = []
                        for doc, dist, meta in combined:
                            doc_normalized = doc.strip().lower()[:100]
                            if doc_normalized not in seen_texts:
                                seen_texts.add(doc_normalized)
                                unique_results.append((doc, dist, meta))
                        
                        unique_results.sort(key=lambda x: x[1])
                        top_results = unique_results[:n_results]
                        docs = [r[0] for r in top_results]
                        distances = [r[1] for r in top_results]
                        metadatas = [r[2] for r in top_results]
                else:
                    # Deduplicate and merge results by distance (semantic only)
                    if all_docs:
                        combined = list(zip(all_docs, all_distances, all_metadatas))
                        seen_texts = set()
                        unique_results = []
                        for doc, dist, meta in combined:
                            doc_normalized = doc.strip().lower()[:100]
                            if doc_normalized not in seen_texts:
                                seen_texts.add(doc_normalized)
                                unique_results.append((doc, dist, meta))
                        
                        unique_results.sort(key=lambda x: x[1])
                        top_results = unique_results[:n_results]
                        docs = [r[0] for r in top_results]
                        distances = [r[1] for r in top_results]
                        metadatas = [r[2] for r in top_results]
                    else:
                        # Fallback to original query
                        query_params = {
                            "query_texts": [query],
                            "n_results": n_results,
                            "include": ['documents', 'distances', 'metadatas']
                        }
                        where_conditions = self._build_where_conditions(document_filters, advanced_filters)
                        if where_conditions:
                            query_params["where"] = where_conditions
                        
                        results = self.processor.collection.query(**query_params)
                        docs = results.get('documents', [[]])[0]
                        distances = results.get('distances', [[]])[0]
                        metadatas = results.get('metadatas', [[]])[0]
            else:
                # Single query (no expansion or expansion returned only original)
                # Use hybrid search if enabled
                if self.enable_hybrid_search:
                    # Perform both semantic and keyword search
                    semantic_docs, semantic_distances, semantic_metadatas = [], [], []
                    keyword_docs, keyword_distances, keyword_metadatas = [], [], []
                    
                    # Semantic search
                    try:
                        query_params = {
                            "query_texts": [query],
                            "n_results": n_results * 2,  # Get more for merging
                            "include": ['documents', 'distances', 'metadatas']
                        }
                        
                        where_conditions = self._build_where_conditions(document_filters, advanced_filters)
                        if where_conditions:
                            query_params["where"] = where_conditions
                        
                        semantic_results = self.processor.collection.query(**query_params)
                        semantic_docs = semantic_results.get('documents', [[]])[0]
                        semantic_distances = semantic_results.get('distances', [[]])[0]
                        semantic_metadatas = semantic_results.get('metadatas', [[]])[0]
                    except Exception as e:
                        print(f"⚠️ Semantic search failed: {e}")
                    
                    # Keyword search
                    try:
                        keyword_docs, keyword_distances, keyword_metadatas = self._keyword_search(
                            query, 
                            k=n_results * 2,  # Get more for merging
                            document_filters=document_filters,
                            advanced_filters=advanced_filters
                        )
                    except Exception as e:
                        print(f"⚠️ Keyword search failed: {e}")
                    
                    # Merge and re-rank results
                    if semantic_docs or keyword_docs:
                        docs, distances, metadatas = self._merge_search_results(
                            semantic_docs, semantic_distances, semantic_metadatas,
                            keyword_docs, keyword_distances, keyword_metadatas,
                            n_results
                        )
                    else:
                        docs, distances, metadatas = [], [], []
                else:
                    # Semantic search only (original behavior)
                    query_params = {
                        "query_texts": [query],
                        "n_results": n_results,
                        "include": ['documents', 'distances', 'metadatas']
                    }
                    
                    where_conditions = self._build_where_conditions(document_filters, advanced_filters)
                    if where_conditions:
                        query_params["where"] = where_conditions
                    
                    results = self.processor.collection.query(**query_params)
                    docs = results.get('documents', [[]])[0]
                    distances = results.get('distances', [[]])[0]
                    metadatas = results.get('metadatas', [[]])[0]
            
            if not docs:
                return "", []
            
            # Re-rank chunks if enabled (improves relevance ordering)
            if self.enable_reranking and len(docs) > 1:
                try:
                    docs, distances, metadatas = self._rerank_chunks(query, docs, distances, metadatas)
                except Exception as e:
                    print(f"⚠️ Re-ranking failed: {e}, using original order")
                    # Continue with original order if re-ranking fails
            
            # Smart filtering: use adaptive threshold - prioritize recall for weak semantic matches
            # (e.g. "summarize the resume" may not match "experience, skills" chunks closely)
            top_distance = distances[0] if distances else 1.0
            threshold = 0.5 if top_distance < 0.3 else 1.0  # Include more results when top match is weak
            
            filtered_docs = []
            filtered_sources = []  # Track sources for each chunk
            total_length = 0
            
            for i, (doc, distance) in enumerate(zip(docs, distances)):
                if distance < threshold and total_length < self.max_context_chars:
                    doc_text = doc.strip() if doc else ""
                    if doc_text:
                        doc_length = len(doc_text)
                        # Stop if adding this doc would exceed limit
                        if total_length + doc_length > self.max_context_chars:
                            # Try to add partial if we have space
                            remaining = self.max_context_chars - total_length
                            if remaining > 200:  # Only if meaningful space remains
                                filtered_docs.append(doc_text[:remaining])
                                # Get source info
                                source_info = metadatas[i] if metadatas and i < len(metadatas) else {}
                                filtered_sources.append({
                                    "source": source_info.get("source", "Unknown"),
                                    "relevance": round(1 - distance, 3),  # Convert distance to relevance score
                                    "distance": round(distance, 3)
                                })
                            break
                        filtered_docs.append(doc_text)
                        total_length += doc_length
                        # Get source info
                        source_info = metadatas[i] if metadatas and i < len(metadatas) else {}
                        filtered_sources.append({
                            "source": source_info.get("source", "Unknown"),
                            "relevance": round(1 - distance, 3),  # Convert distance to relevance score
                            "distance": round(distance, 3)
                        })
            
            # If no docs passed threshold, use top result anyway (fallback)
            if not filtered_docs and docs:
                # Use at least the top result even if below threshold
                top_doc = docs[0].strip() if docs[0] else ""
                if top_doc:
                    filtered_docs = [top_doc[:self.max_context_chars]]
                    if metadatas and len(metadatas) > 0:
                        source_info = metadatas[0]
                        filtered_sources = [{
                            "source": source_info.get("source", "Unknown"),
                            "relevance": round(1 - distances[0], 3) if distances else 0.5,
                            "distance": round(distances[0], 3) if distances else 0.5
                        }]
            
            if not filtered_docs:
                return "", []
            
            # Join with minimal separator for efficiency
            context = "\n\n".join(filtered_docs)
            
            # Summarize context if it exceeds the threshold
            if self.enable_context_summarization:
                context = self.summarize_context(context, query=query)
            
            # Deduplicate sources and sort by relevance
            unique_sources = {}
            for source in filtered_sources:
                source_name = source["source"]
                if source_name not in unique_sources or source["relevance"] > unique_sources[source_name]["relevance"]:
                    unique_sources[source_name] = source
            
            # Sort by relevance (highest first)
            sorted_sources = sorted(unique_sources.values(), key=lambda x: x["relevance"], reverse=True)
            
            return context[:self.max_context_chars], sorted_sources  # Final safety trim

        except Exception as e:
            print(f"❌ Error retrieving context: {type(e).__name__}: {e}")
            return "", []

    def _build_where_conditions(self, document_filters=None, advanced_filters=None):
        """Build where conditions for ChromaDB query filtering."""
        where_conditions = {}
        
        # Handle legacy document_filters
        if document_filters and len(document_filters) > 0:
            if len(document_filters) == 1:
                where_conditions["source"] = document_filters[0]
            else:
                where_conditions["source"] = {"$in": document_filters}
        
        # Handle advanced filters
        if advanced_filters:
            conditions = []
            
            # Document name filters
            if advanced_filters.document_names and len(advanced_filters.document_names) > 0:
                if len(advanced_filters.document_names) == 1:
                    conditions.append({"source": advanced_filters.document_names[0]})
                else:
                    conditions.append({"source": {"$in": advanced_filters.document_names}})
            
            # File type filters
            if advanced_filters.file_types and len(advanced_filters.file_types) > 0:
                if len(advanced_filters.file_types) == 1:
                    conditions.append({"file_type": advanced_filters.file_types[0]})
                else:
                    conditions.append({"file_type": {"$in": advanced_filters.file_types}})
            
            # Date range filters
            if advanced_filters.date_from or advanced_filters.date_to:
                date_condition = {}
                if advanced_filters.date_from:
                    date_condition["$gte"] = advanced_filters.date_from
                if advanced_filters.date_to:
                    date_condition["$lte"] = advanced_filters.date_to
                if date_condition:
                    conditions.append({"processing_date": date_condition})
            
            # Combine conditions with AND logic
            if conditions:
                if len(conditions) == 1:
                    where_conditions.update(conditions[0])
                else:
                    # ChromaDB uses $and for multiple conditions
                    where_conditions = {"$and": conditions}
            
            # Exclude documents
            if advanced_filters.exclude_documents and len(advanced_filters.exclude_documents) > 0:
                if "source" in where_conditions:
                    # If we already have source filter, we need to combine
                    existing_sources = where_conditions.get("source", {})
                    if isinstance(existing_sources, dict) and "$in" in existing_sources:
                        # Filter out excluded documents
                        existing_sources["$in"] = [s for s in existing_sources["$in"] 
                                                  if s not in advanced_filters.exclude_documents]
                    elif isinstance(existing_sources, str):
                        # Single source, check if it should be excluded
                        if existing_sources in advanced_filters.exclude_documents:
                            where_conditions = {}  # No results if only source is excluded
                else:
                    # Add exclusion filter
                    if len(advanced_filters.exclude_documents) == 1:
                        where_conditions["source"] = {"$ne": advanced_filters.exclude_documents[0]}
                    else:
                        # Need to use $and with $nin (not in)
                        if "$and" in where_conditions:
                            where_conditions["$and"].append({"source": {"$nin": advanced_filters.exclude_documents}})
                        else:
                            where_conditions["source"] = {"$nin": advanced_filters.exclude_documents}
        
        if where_conditions:
            print(f"🔍 Applying filters: {where_conditions}")
        
        return where_conditions

    def _extract_keywords(self, query):
        """Extract meaningful keywords from a query for keyword search.
        
        Args:
            query: The search query
            
        Returns:
            List of keywords (lowercased, without stop words)
        """
        # Simple stop words list
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
            'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be', 'been', 'being', 'have', 'has',
            'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could', 'may', 'might', 'can',
            'this', 'that', 'these', 'those', 'what', 'which', 'who', 'whom', 'whose', 'where',
            'when', 'why', 'how', 'if', 'then', 'than', 'so', 'because', 'about', 'into', 'through'
        }
        
        # Extract words (alphanumeric sequences)
        words = re.findall(r'\b\w+\b', query.lower())
        
        # Filter out stop words and short words
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        
        return keywords if keywords else words[:5]  # Fallback to first 5 words if all are stop words

    def _keyword_search(self, query, k=4, document_filters=None, advanced_filters=None):
        """Perform keyword-based search on document chunks.
        
        Args:
            query: The search query
            k: Number of results to retrieve
            document_filters: Optional list of document filenames to filter by
            advanced_filters: Optional AdvancedSearchFilters object for advanced filtering
            
        Returns:
            Tuple of (documents, distances, metadatas) lists
        """
        try:
            # Extract keywords from query
            keywords = self._extract_keywords(query)
            if not keywords:
                return [], [], []
            
            # Build where conditions
            where_conditions = self._build_where_conditions(document_filters, advanced_filters)
            
            # Get chunks with filters applied
            try:
                if where_conditions:
                    all_results = self.processor.collection.get(
                        where=where_conditions,
                        limit=min(1000, self.processor.collection.count()),
                        include=['documents', 'metadatas']
                    )
                else:
                    all_results = self.processor.collection.get(
                        limit=min(1000, self.processor.collection.count()),
                        include=['documents', 'metadatas']
                    )
            except Exception as e:
                print(f"⚠️ Error fetching chunks for keyword search: {e}")
                return [], [], []
            
            if not all_results or not all_results.get('documents'):
                return [], [], []
            
            documents = all_results.get('documents', [])
            metadatas = all_results.get('metadatas', [])
            
            # Score documents based on keyword matches
            scored_docs = []
            for i, doc in enumerate(documents):
                if not doc:
                    continue
                
                doc_lower = doc.lower()
                score = 0
                matched_keywords = 0
                
                # Calculate keyword match score
                for keyword in keywords:
                    # Exact word match (higher score)
                    if re.search(r'\b' + re.escape(keyword) + r'\b', doc_lower):
                        score += 2
                        matched_keywords += 1
                    # Substring match (lower score)
                    elif keyword in doc_lower:
                        score += 1
                
                # Normalize score by document length and keyword count
                if matched_keywords > 0:
                    # Bonus for matching more keywords
                    keyword_coverage = matched_keywords / len(keywords)
                    # Penalize very long documents
                    length_penalty = min(1.0, 500 / max(len(doc), 1))
                    
                    final_score = score * keyword_coverage * length_penalty
                    scored_docs.append((doc, final_score, metadatas[i] if i < len(metadatas) else {}))
            
            # Sort by score (descending) and take top k
            scored_docs.sort(key=lambda x: x[1], reverse=True)
            top_docs = scored_docs[:k]
            
            if not top_docs:
                return [], [], []
            
            # Convert scores to distances (inverse for compatibility)
            # Higher score = lower distance
            max_score = max(score for _, score, _ in top_docs) if top_docs else 1.0
            distances = [1.0 - (score / max(1.0, max_score)) for _, score, _ in top_docs]
            documents = [doc for doc, _, _ in top_docs]
            metadatas = [meta for _, _, meta in top_docs]
            
            return documents, distances, metadatas
            
        except Exception as e:
            print(f"⚠️ Keyword search failed: {e}")
            return [], [], []

    def _merge_search_results(self, semantic_docs, semantic_distances, semantic_metadatas,
                              keyword_docs, keyword_distances, keyword_metadatas, k):
        """Merge and re-rank results from semantic and keyword search.
        
        Args:
            semantic_docs, semantic_distances, semantic_metadatas: Results from semantic search
            keyword_docs, keyword_distances, keyword_metadatas: Results from keyword search
            k: Number of final results to return
            
        Returns:
            Tuple of (merged_docs, merged_distances, merged_metadatas)
        """
        # Combine results with source tags
        all_results = []
        
        # Add semantic results (weight: 0.6)
        for doc, dist, meta in zip(semantic_docs, semantic_distances, semantic_metadatas):
            if doc:
                # Normalize distance to 0-1 range and apply weight
                normalized_dist = min(1.0, dist)
                weighted_score = 1.0 - (normalized_dist * 0.6)  # Higher score = better
                all_results.append((doc, weighted_score, meta, 'semantic'))
        
        # Add keyword results (weight: 0.4)
        for doc, dist, meta in zip(keyword_docs, keyword_distances, keyword_metadatas):
            if doc:
                # Normalize distance to 0-1 range and apply weight
                normalized_dist = min(1.0, dist)
                weighted_score = 1.0 - (normalized_dist * 0.4)  # Higher score = better
                all_results.append((doc, weighted_score, meta, 'keyword'))
        
        if not all_results:
            return [], [], []
        
        # Deduplicate by content
        seen_texts = set()
        unique_results = []
        for doc, score, meta, source in all_results:
            doc_normalized = doc.strip().lower()[:150]  # Use first 150 chars for dedup
            if doc_normalized not in seen_texts:
                seen_texts.add(doc_normalized)
                unique_results.append((doc, score, meta, source))
            else:
                # If duplicate found, boost score if it came from both sources
                for i, (existing_doc, existing_score, existing_meta, existing_source) in enumerate(unique_results):
                    if existing_doc.strip().lower()[:150] == doc_normalized:
                        # Boost score if found in both semantic and keyword search
                        if existing_source != source:
                            unique_results[i] = (existing_doc, min(1.0, existing_score + 0.2), existing_meta, 'hybrid')
                        break
        
        # Sort by score (descending) and take top k
        unique_results.sort(key=lambda x: x[1], reverse=True)
        top_results = unique_results[:k]
        
        # Convert scores back to distances for compatibility
        max_score = max(score for _, score, _, _ in top_results) if top_results else 1.0
        distances = [1.0 - (score / max(1.0, max_score)) for _, score, _, _ in top_results]
        docs = [doc for doc, _, _, _ in top_results]
        metadatas = [meta for _, _, meta, _ in top_results]
        
        if len(semantic_docs) > 0 or len(keyword_docs) > 0:
            print(f"🔀 Hybrid search: {len(semantic_docs)} semantic + {len(keyword_docs)} keyword → {len(docs)} merged results")
        
        return docs, distances, metadatas

    def _rerank_chunks(self, query, docs, distances, metadatas):
        """Re-rank retrieved chunks to improve relevance ordering.
        
        Uses a combination of heuristic scoring and optional LLM-based scoring
        to re-order chunks by relevance to the query.
        
        Args:
            query: The original search query
            docs: List of document chunks
            distances: List of distance scores (from retrieval)
            metadatas: List of metadata dictionaries
            
        Returns:
            Tuple of (reordered_docs, reordered_distances, reordered_metadatas)
        """
        if not docs or len(docs) <= 1:
            return docs, distances, metadatas
        
        try:
            # Extract keywords from query for heuristic scoring
            keywords = self._extract_keywords(query)
            query_lower = query.lower()
            
            # Score each chunk using multiple heuristics
            scored_chunks = []
            for i, (doc, distance, meta) in enumerate(zip(docs, distances, metadatas)):
                if not doc:
                    continue
                
                doc_lower = doc.lower()
                doc_stripped = doc.strip()
                
                # Heuristic 1: Keyword density (higher = better)
                keyword_score = 0.0
                keyword_matches = 0
                for keyword in keywords:
                    # Exact word match (higher weight)
                    word_matches = len(re.findall(r'\b' + re.escape(keyword) + r'\b', doc_lower))
                    keyword_score += word_matches * 2.0
                    if word_matches > 0:
                        keyword_matches += 1
                    # Substring match (lower weight)
                    elif keyword in doc_lower:
                        keyword_score += 0.5
                
                # Normalize keyword score by document length
                doc_length = len(doc_stripped)
                keyword_density = keyword_score / max(1, doc_length / 100)  # Normalize per 100 chars
                
                # Heuristic 2: Query term coverage (how many query keywords appear)
                coverage = keyword_matches / max(1, len(keywords)) if keywords else 0.5
                
                # Heuristic 3: Original distance (from retrieval) - lower is better
                # Convert to relevance score (1 - distance)
                original_relevance = 1.0 - min(1.0, distance)
                
                # Heuristic 4: Query-document overlap (simple word overlap)
                query_words = set(re.findall(r'\b\w+\b', query_lower))
                doc_words = set(re.findall(r'\b\w+\b', doc_lower))
                if query_words:
                    word_overlap = len(query_words & doc_words) / len(query_words)
                else:
                    word_overlap = 0.0
                
                # Heuristic 5: Document position bonus (earlier chunks might be more relevant)
                # This is a small bonus, assuming chunks are roughly in document order
                position_bonus = 1.0 - (i / max(1, len(docs))) * 0.1  # Up to 10% bonus
                
                # Combine heuristics with weights
                # Original relevance: 40% (trust the retrieval system)
                # Keyword density: 25% (exact matches matter)
                # Coverage: 15% (matching more keywords is better)
                # Word overlap: 15% (general term matching)
                # Position: 5% (small bonus for earlier chunks)
                
                combined_score = (
                    original_relevance * 0.4 +
                    min(1.0, keyword_density) * 0.25 +
                    coverage * 0.15 +
                    word_overlap * 0.15 +
                    position_bonus * 0.05
                )
                
                scored_chunks.append((doc, combined_score, distance, meta, i))
            
            # Sort by combined score (descending)
            scored_chunks.sort(key=lambda x: x[1], reverse=True)
            
            # For top chunks, optionally use LLM for fine-grained scoring
            # This is more expensive, so only do it for top candidates
            top_n_for_llm = min(5, len(scored_chunks))
            if top_n_for_llm > 0 and len(query.strip()) > 10:
                try:
                    # Use LLM to score top candidates
                    llm_scored = []
                    for doc, heuristic_score, distance, meta, orig_idx in scored_chunks[:top_n_for_llm]:
                        # Quick LLM relevance check
                        relevance_prompt = (
                            f"Query: {query}\n\n"
                            f"Document excerpt: {doc[:300]}...\n\n"
                            "Rate the relevance of this document excerpt to the query on a scale of 0.0 to 1.0. "
                            "Respond with ONLY a decimal number between 0.0 and 1.0, nothing else."
                        )
                        try:
                            llm_score_text = self._llm_chat(
                                messages=[
                                    {"role": "system", "content": "You are a relevance scorer. Respond with only a number between 0.0 and 1.0."},
                                    {"role": "user", "content": relevance_prompt}
                                ],
                                temperature=0.1,
                                max_tokens=10
                            )
                            # Extract number from response
                            llm_score_match = re.search(r'0?\.\d+|1\.0|0', llm_score_text)
                            if llm_score_match:
                                llm_score = float(llm_score_match.group())
                                # Blend LLM score with heuristic score (70% LLM, 30% heuristic)
                                final_score = llm_score * 0.7 + heuristic_score * 0.3
                            else:
                                final_score = heuristic_score
                        except Exception:
                            # If LLM scoring fails, use heuristic score
                            final_score = heuristic_score
                        
                        llm_scored.append((doc, final_score, distance, meta, orig_idx))
                    
                    # Sort LLM-scored chunks
                    llm_scored.sort(key=lambda x: x[1], reverse=True)
                    
                    # Combine: LLM-scored top chunks + remaining heuristic-scored chunks
                    remaining_chunks = scored_chunks[top_n_for_llm:]
                    final_chunks = llm_scored + remaining_chunks
                except Exception as e:
                    print(f"⚠️ LLM re-ranking failed: {e}, using heuristic scores only")
                    final_chunks = scored_chunks
            else:
                final_chunks = scored_chunks
            
            # Extract reordered lists
            reordered_docs = [chunk[0] for chunk in final_chunks]
            # Convert scores back to distances for compatibility
            # Higher score = lower distance
            max_score = max(chunk[1] for chunk in final_chunks) if final_chunks else 1.0
            reordered_distances = [1.0 - (chunk[1] / max(1.0, max_score)) for chunk in final_chunks]
            reordered_metadatas = [chunk[3] for chunk in final_chunks]
            
            print(f"🔄 Re-ranked {len(reordered_docs)} chunks")
            
            return reordered_docs, reordered_distances, reordered_metadatas
            
        except Exception as e:
            print(f"⚠️ Re-ranking error: {e}")
            return docs, distances, metadatas  # Return original order on error

    def expand_query(self, query):
        """Expand and rewrite query to improve retrieval accuracy.
        
        Generates alternative phrasings and key terms to improve semantic search.
        Returns a list of query variations including the original.
        
        Args:
            query: The original user query
            
        Returns:
            List of query strings (original + variations)
        """
        # Rule-based expansion for summarization queries (no LLM, always runs)
        # "Summarize X" rarely matches document content; add content-focused terms
        q_lower = query.lower().strip()
        summarization_words = ("summarize", "summary", "overview", "sum up", "recap", "summarise")
        if any(w in q_lower for w in summarization_words):
            content_query = "contents overview key sections experience skills education qualifications main points"
            return [query, content_query]

        if not self.enable_query_expansion:
            return [query]
        
        # Skip expansion for very short queries (likely to be less effective)
        if len(query.strip()) < 10:
            return [query]
        
        try:
            # Use LLM to generate query variations
            expansion_prompt = (
                f"Given this question: '{query}'\n\n"
                "Generate 2-3 alternative phrasings or rewordings of this question that mean the same thing. "
                "Focus on:\n"
                "- Using synonyms and related terms\n"
                "- Different question structures\n"
                "- Key concepts and entities\n\n"
                "Return ONLY the alternative phrasings, one per line, without numbering or bullets. "
                "Keep them concise (under 20 words each)."
            )
            
            # Add timeout to prevent hanging (15 seconds max for query expansion)
            # Use concurrent.futures for timeout control
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
            
            def call_llm():
                return self._llm_chat(
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that rewrites questions to improve search results."},
                        {"role": "user", "content": expansion_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=150
                )
            
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(call_llm)
                    expanded_text = future.result(timeout=15.0)  # 15 second timeout
            except FuturesTimeoutError:
                print(f"⚠️ Query expansion timed out after 15s (falling back to original query)")
                return [query]  # Fallback to original query on timeout
            except Exception as e:
                print(f"⚠️ Query expansion failed (falling back to original query): {type(e).__name__}: {e}")
                return [query]  # Fallback to original query on any error
            
            # Parse the expanded queries
            variations = []
            if expanded_text:
                # Split by newlines and clean up
                lines = expanded_text.split('\n')
                for line in lines:
                    line = line.strip()
                    # Remove numbering, bullets, dashes
                    line = line.lstrip('0123456789.-•* ').strip()
                    if line and len(line) > 5:  # Valid variation
                        variations.append(line)
            
            # Combine original with variations
            all_queries = [query] + variations[:3]  # Limit to 3 variations
            
            # Remove duplicates while preserving order
            seen = set()
            unique_queries = []
            for q in all_queries:
                q_lower = q.lower().strip()
                if q_lower not in seen and len(q_lower) > 3:
                    seen.add(q_lower)
                    unique_queries.append(q)
            
            if len(unique_queries) > 1:
                print(f"✨ Expanded query '{query[:50]}{'...' if len(query) > 50 else ''}' into {len(unique_queries)} variations")
            return unique_queries if len(unique_queries) > 1 else [query]

        except Exception as e:
            print(f"⚠️ Query expansion failed: {e}, using original query")
            return [query]

    def summarize_context(self, context: str, query: str = "", max_length: Optional[int] = None) -> str:
        """Summarize context if it exceeds the maximum length threshold.
        
        Uses LLM to create a concise summary while preserving key facts and information
        relevant to the query.
        
        Args:
            context: The context text to potentially summarize
            query: The user query (optional, used to focus summarization)
            max_length: Optional override for maximum length (defaults to max_context_chars)
            
        Returns:
            Summarized context if it exceeded threshold, otherwise original context
        """
        if not self.enable_context_summarization:
            return context
        
        # Use provided max_length or default to max_context_chars
        target_length = max_length if max_length is not None else self.max_context_chars
        
        # Calculate threshold
        threshold = int(target_length * self.summarization_threshold)
        
        # If context is within threshold, return as-is
        if len(context) <= threshold:
            return context
        
        try:
            print(f"📝 Summarizing context ({len(context)} chars -> target: {target_length} chars)")
            
            # Limit context length for summarization to avoid token limits
            # Use first portion of context if it's extremely long
            context_for_summary = context
            max_context_for_llm = min(len(context), target_length * 4)  # Allow 4x for input
            if len(context) > max_context_for_llm:
                context_for_summary = context[:max_context_for_llm] + "\n\n[... additional content truncated ...]"
            
            # Prepare summarization prompt
            # Include query if available to focus the summary
            if query and len(query.strip()) > 0:
                summary_prompt = (
                    f"User question: {query}\n\n"
                    f"Context to summarize:\n{context_for_summary}\n\n"
                    "Create a concise summary of this context that:\n"
                    "- Preserves all key facts and important information\n"
                    "- Maintains specific details, numbers, dates, and names\n"
                    "- Focuses on information relevant to the user's question\n"
                    "- Removes redundancy and less important details\n"
                    f"- Keeps the summary under {target_length} characters\n\n"
                    "Provide only the summarized context, no additional commentary:"
                )
            else:
                summary_prompt = (
                    f"Summarize the following context while preserving all key facts:\n\n{context_for_summary}\n\n"
                    "Requirements:\n"
                    "- Keep all important information, facts, numbers, dates, and names\n"
                    "- Remove redundancy and less critical details\n"
                    "- Make it concise but complete\n"
                    f"- Target length: under {target_length} characters\n\n"
                    "Provide only the summary:"
                )
            
            # Use LLM to summarize
            summarized = self._llm_chat(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a context summarizer. Create concise summaries that preserve all key facts and important information."
                    },
                    {
                        "role": "user",
                        "content": summary_prompt
                    }
                ],
                temperature=0.2,
                max_tokens=target_length + 200
            )
            
            # Validate summary
            if not summarized or len(summarized) < 50:
                print("⚠️ Summarization produced invalid result, using truncated original context")
                return context[:target_length]  # Fallback to truncation
            
            # If summary is still too long, truncate it
            if len(summarized) > target_length:
                print(f"⚠️ Summary still too long ({len(summarized)} chars), truncating")
                summarized = summarized[:target_length]
            
            print(f"✅ Context summarized: {len(context)} -> {len(summarized)} chars")
            return summarized
            
        except Exception as e:
            print(f"⚠️ Context summarization failed: {e}, using truncated original")
            # Fallback to simple truncation
            return context[:target_length]

    def generate_response(self, query, context, is_followup=False, intent=None):
        """Generate response with optimized prompt and optional streaming.
        
        Args:
            query: The user query
            context: Retrieved context from knowledge base
            is_followup: Whether this is a follow-up question
            intent: Query intent classification result (dict with 'intent' and 'confidence')
        """
        # Build prompt with follow-up awareness and intent-specific guidance
        intent_guidance = ""
        if intent and intent.get("intent"):
            intent_type = intent.get("intent", "factual")
            if intent_type == "how_to":
                intent_guidance = "\n\nNote: This is a 'how-to' question. Provide clear, step-by-step instructions if available in the context."
            elif intent_type == "definition":
                intent_guidance = "\n\nNote: This is a definition question. Provide a clear, concise definition."
            elif intent_type == "comparison":
                intent_guidance = "\n\nNote: This is a comparison question. Highlight differences and similarities clearly."
            elif intent_type == "list":
                intent_guidance = "\n\nNote: This is a list question. Present information as a clear, organized list."
            elif intent_type == "explanation":
                intent_guidance = "\n\nNote: This is an explanation question. Explain the reasoning or mechanism clearly."
            elif intent_type == "verification":
                intent_guidance = "\n\nNote: This is a verification question. Provide a clear yes/no answer with supporting evidence."
        
        style_rules = (
            "\n\nStyle rules:\n"
            "- Provide ONLY the answer.\n"
            "- Do NOT say phrases like 'as mentioned in the context', 'as mentioned in your context', 'based on the context', or similar.\n"
            "- Do NOT mention that you used the context.\n"
            "- If context is empty, answer using general knowledge.\n"
        )

        if is_followup:
            user_message = (
                f"Context from knowledge base:\n{context}\n\n"
                f"Current question: {query}\n\n"
                f"Note: This is a follow-up question. Use the conversation history above to understand "
                f"what the user is referring to. Answer the question using both the provided context "
                f"and the conversation history.{intent_guidance}{style_rules}\n\nAnswer:"
            )
        else:
            user_message = f"Context:\n{context}\n\nQuestion: {query}{intent_guidance}{style_rules}\n\nAnswer:"
        
        # Use conversation history (up to last 4 exchanges for follow-ups, 2 for new questions)
        max_history = 8 if is_followup else 4
        recent_history = self.chat_history[-max_history:] if len(self.chat_history) > max_history else self.chat_history
        messages = recent_history + [{"role": "user", "content": user_message}]

        try:
            # Use unified LLM chat method (supports Groq, OpenAI, Ollama)
            answer = self._llm_chat(
                messages=messages,
                stream=self.enable_streaming,
                temperature=0.3,
                max_tokens=180
            )

            # Clean up style boilerplate (user does not want it)
            answer = self._clean_answer_style(answer)

            # Update history (keep it minimal)
            if len(self.chat_history) > 6:  # Keep only last 3 exchanges
                self.chat_history = self.chat_history[0:1] + self.chat_history[-5:]
            
            self.chat_history.append({"role": "user", "content": query})
            self.chat_history.append({"role": "assistant", "content": answer})
            
            return answer

        except Exception as e:
            return f"❌ Error: {str(e)}"
    
    def generate_response_stream(self, query, context, is_followup=False):
        """Generate response as a stream of chunks (generator)."""
        # Build prompt with follow-up awareness
        style_rules = (
            "\n\nStyle rules:\n"
            "- Provide ONLY the answer.\n"
            "- Do NOT say phrases like 'as mentioned in the context', 'as mentioned in your context', 'based on the context', or similar.\n"
            "- Do NOT mention that you used the context.\n"
            "- If context is empty, answer using general knowledge.\n"
        )

        if is_followup:
            user_message = (
                f"Context from knowledge base:\n{context}\n\n"
                f"Current question: {query}\n\n"
                f"Note: This is a follow-up question. Use the conversation history above to understand "
                f"what the user is referring to. Answer the question using both the provided context "
                f"and the conversation history.{style_rules}\n\nAnswer:"
            )
        else:
            user_message = f"Context:\n{context}\n\nQuestion: {query}{style_rules}\n\nAnswer:"
        
        # Use conversation history (up to last 4 exchanges for follow-ups, 2 for new questions)
        max_history = 8 if is_followup else 4
        recent_history = self.chat_history[-max_history:] if len(self.chat_history) > max_history else self.chat_history
        messages = recent_history + [{"role": "user", "content": user_message}]

        try:
            response_text = ""
            # Buffer initial output so we can strip leading boilerplate before user sees it in streaming
            prefix_buffer = ""
            started = False
            
            # Use unified LLM streaming method (supports Groq, OpenAI, Ollama)
            for content in self._llm_chat_stream(messages=messages, temperature=0.3, max_tokens=180):
                response_text += content

                if not started:
                    prefix_buffer += content
                    # Once we have enough text to decide, strip leading boilerplate once
                    if len(prefix_buffer) >= 80 or prefix_buffer.strip().endswith((".", ":", "\n")):
                        cleaned = self._clean_answer_style(prefix_buffer)
                        # If cleaning removed everything (rare), keep buffering a bit more
                        if cleaned.strip():
                            started = True
                            yield cleaned
                            prefix_buffer = ""
                    continue

                yield content
            
            # Flush any remaining buffer if stream ended early
            if not started and prefix_buffer:
                cleaned = self._clean_answer_style(prefix_buffer)
                if cleaned.strip():
                    yield cleaned
            
            # Clean up common prefixes after streaming completes
            answer = response_text.strip()
            answer = self._clean_answer_style(answer)

            # Update history (keep it minimal)
            if len(self.chat_history) > 6:  # Keep only last 3 exchanges
                self.chat_history = self.chat_history[0:1] + self.chat_history[-5:]
            
            self.chat_history.append({"role": "user", "content": query})
            self.chat_history.append({"role": "assistant", "content": answer})
            
        except Exception as e:
            yield f"❌ Error: {str(e)}"

    def _is_complex_query(self, query: str, intent_info: dict) -> bool:
        """Determine if a query requires multi-step reasoning.
        
        Args:
            query: The user query
            intent_info: Query intent classification result
            
        Returns:
            True if query is complex enough for multi-step reasoning
        """
        if not self.enable_multi_step_reasoning:
            return False
        
        # Skip for very short queries
        if len(query.strip()) < 20:
            return False
        
        # Check intent - some intents are more likely to need multi-step reasoning
        intent_type = intent_info.get("intent", "factual")
        complex_intents = ["comparison", "explanation", "analysis"]
        if intent_type in complex_intents:
            return True
        
        # Check for indicators of complex queries
        complex_indicators = [
            "compare", "difference", "similar", "versus", "vs",
            "why", "how does", "explain how", "what causes",
            "relationship between", "connection between",
            "step by step", "process", "workflow",
            "multiple", "several", "various", "different",
            "and", "also", "additionally", "furthermore"
        ]
        
        query_lower = query.lower()
        indicator_count = sum(1 for indicator in complex_indicators if indicator in query_lower)
        
        # Check for multiple question marks or multiple clauses
        question_marks = query.count("?")
        conjunctions = [" and ", " or ", " but ", " then ", " after ", " before "]
        conjunction_count = sum(1 for conj in conjunctions if conj in query_lower)
        
        # Use LLM to determine complexity if indicators are ambiguous
        if indicator_count >= 2 or question_marks > 1 or conjunction_count >= 2:
            try:
                complexity_prompt = (
                    f"Question: {query}\n\n"
                    "Does this question require breaking down into multiple sub-questions to answer properly? "
                    "Consider if it:\n"
                    "- Asks about multiple things that need separate investigation\n"
                    "- Requires comparing or analyzing different aspects\n"
                    "- Needs step-by-step reasoning or explanation\n"
                    "- Involves understanding relationships or processes\n\n"
                    "Respond with ONLY 'yes' or 'no'."
                )
                
                answer = self._llm_chat(
                    messages=[
                        {"role": "system", "content": "You are a query complexity analyzer. Respond with only 'yes' or 'no'."},
                        {"role": "user", "content": complexity_prompt}
                    ],
                    temperature=0.1,
                    max_tokens=5
                ).lower()
                return "yes" in answer
            except Exception as e:
                print(f"⚠️ Complexity check failed: {e}, defaulting to simple query")
                # Default to complex if we have strong indicators
                return indicator_count >= 2 or conjunction_count >= 2
        
        return False

    def _decompose_query(self, query: str) -> list:
        """Break down a complex query into sub-questions.
        
        Args:
            query: The complex query to decompose
            
        Returns:
            List of sub-questions/steps
        """
        try:
            decomposition_prompt = (
                f"Complex question: {query}\n\n"
                "Break this question down into 2-4 specific sub-questions that need to be answered "
                "to fully address the original question. Each sub-question should:\n"
                "- Be clear and specific\n"
                "- Focus on one aspect of the original question\n"
                "- Be answerable independently\n"
                "- Together, cover all aspects of the original question\n\n"
                "Return ONLY the sub-questions, one per line, without numbering, bullets, or dashes. "
                "Each sub-question should be a complete question ending with '?'."
            )
            
            decomposed_text = self._llm_chat(
                messages=[
                    {"role": "system", "content": "You are a query decomposition assistant. Break complex questions into clear sub-questions."},
                    {"role": "user", "content": decomposition_prompt}
                ],
                temperature=0.3,
                max_tokens=200
            )
            
            # Parse sub-questions
            sub_questions = []
            if decomposed_text:
                lines = decomposed_text.split('\n')
                for line in lines:
                    line = line.strip()
                    # Remove numbering, bullets, dashes
                    line = re.sub(r'^[\d.\-•*\s]+', '', line).strip()
                    if line and line.endswith('?'):
                        sub_questions.append(line)
                    elif line and len(line) > 10:
                        # If it doesn't end with ?, add it
                        if not line.endswith('?'):
                            line += "?"
                        sub_questions.append(line)
            
            # Fallback: if decomposition failed, return original query
            if not sub_questions:
                print("⚠️ Query decomposition failed, using original query")
                return [query]
            
            # Limit to 4 sub-questions to avoid excessive processing
            return sub_questions[:4]
            
        except Exception as e:
            print(f"⚠️ Error decomposing query: {e}")
            return [query]  # Fallback to original query

    def _synthesize_answer(self, original_query: str, sub_answers: list, sub_questions: list) -> str:
        """Synthesize sub-answers into a coherent final answer.
        
        Args:
            original_query: The original complex query
            sub_answers: List of answers to sub-questions
            sub_questions: List of sub-questions that were answered
            
        Returns:
            Synthesized final answer
        """
        try:
            # Prepare synthesis prompt
            sub_qa_pairs = []
            for i, (question, answer) in enumerate(zip(sub_questions, sub_answers), 1):
                sub_qa_pairs.append(f"Sub-question {i}: {question}\nAnswer: {answer}")
            
            synthesis_prompt = (
                f"Original question: {original_query}\n\n"
                "The following sub-questions were answered:\n\n"
                + "\n\n".join(sub_qa_pairs) +
                "\n\n"
                "Synthesize these answers into a comprehensive, coherent answer to the original question. "
                "The final answer should:\n"
                "- Directly address the original question\n"
                "- Integrate information from all sub-answers\n"
                "- Be well-organized and easy to follow\n"
                "- Avoid repetition\n"
                "- Maintain accuracy and cite relevant details\n\n"
                "Provide the synthesized answer:"
            )
            
            synthesized = self._llm_chat(
                messages=[
                    {"role": "system", "content": "You are a synthesis assistant that combines multiple answers into a coherent response."},
                    {"role": "user", "content": synthesis_prompt}
                ],
                temperature=0.4,
                max_tokens=600
            )
            
            # Fallback: if synthesis fails, combine answers with structure
            if not synthesized or len(synthesized) < 50:
                print("⚠️ Synthesis failed, using structured combination")
                combined = f"Based on the analysis:\n\n"
                for i, (question, answer) in enumerate(zip(sub_questions, sub_answers), 1):
                    combined += f"{i}. {answer}\n\n"
                return combined.strip()
            
            return synthesized
            
        except Exception as e:
            print(f"⚠️ Error synthesizing answer: {e}")
            # Fallback: simple combination
            return "\n\n".join([f"• {ans}" for ans in sub_answers if ans])

    def multi_step_reasoning(self, query: str, document_filters=None, advanced_filters=None, conversation_context=None) -> tuple:
        """Perform multi-step reasoning for complex queries.
        
        Args:
            query: The complex query
            document_filters: Optional document filters
            advanced_filters: Optional advanced filters
            conversation_context: Optional conversation context
            
        Returns:
            Tuple of (answer, sources, intent_info)
        """
        print(f"🧠 Multi-step reasoning activated for: {query[:80]}...")
        
        # Step 1: Decompose query into sub-questions
        sub_questions = self._decompose_query(query)
        print(f"📋 Decomposed into {len(sub_questions)} sub-questions")
        
        # Step 2: Answer each sub-question
        sub_answers = []
        all_sources = []
        sub_intents = []
        
        for i, sub_q in enumerate(sub_questions, 1):
            print(f"  Step {i}/{len(sub_questions)}: {sub_q[:60]}...")
            
            # Retrieve context for this sub-question
            sub_context, sub_sources = self.retrieve_context(
                sub_q,
                k=4,  # Use standard k for sub-questions
                document_filters=document_filters,
                advanced_filters=advanced_filters
            )
            
            if not sub_context:
                sub_answers.append(self.generate_response(sub_q, "", is_followup=False))
                continue
            
            # Generate answer for sub-question
            try:
                # Classify intent for sub-question (if method exists)
                try:
                    sub_intent = self.classify_query_intent(sub_q)
                except AttributeError:
                    # If classify_query_intent doesn't exist, use default
                    sub_intent = {"intent": "factual", "confidence": 0.5}
                
                sub_intents.append(sub_intent)
                
                # Generate response (without follow-up context for sub-questions)
                sub_answer = self.generate_response(
                    sub_q,
                    sub_context,
                    is_followup=False,
                    intent=sub_intent
                )
                sub_answers.append(sub_answer)
                
                # Collect sources
                all_sources.extend(sub_sources)
                
            except Exception as e:
                print(f"⚠️ Error answering sub-question {i}: {e}")
                sub_answers.append(f"Error processing: {sub_q}")
        
        # Step 3: Synthesize final answer
        print("🔗 Synthesizing final answer...")
        final_answer = self._synthesize_answer(query, sub_answers, sub_questions)
        
        # Deduplicate and sort sources
        unique_sources = {}
        for source in all_sources:
            source_name = source.get("source", "Unknown")
            if source_name not in unique_sources or source.get("relevance", 0) > unique_sources[source_name].get("relevance", 0):
                unique_sources[source_name] = source
        
        sorted_sources = sorted(unique_sources.values(), key=lambda x: x.get("relevance", 0), reverse=True)
        
        # Use most common intent from sub-questions, or default
        if sub_intents:
            intent_counts = Counter([intent.get("intent", "factual") for intent in sub_intents])
            most_common_intent = intent_counts.most_common(1)[0][0]
            intent_info = {"intent": most_common_intent, "confidence": 0.7}
        else:
            intent_info = {"intent": "factual", "confidence": 0.5}
        
        # Calculate confidence for multi-step reasoning answer
        confidence_info = None
        if self.enable_confidence_scoring:
            # For multi-step, confidence is based on all sub-answers
            # Use average of sub-answer confidences or calculate overall
            try:
                # Calculate confidence based on final answer
                confidence_info = self.score_answer_confidence(
                    query, 
                    final_answer, 
                    "\n\n".join(sub_answers),  # Use all sub-answers as context
                    sorted_sources
                )
                # Multi-step reasoning typically has higher confidence due to thoroughness
                # Boost confidence slightly
                if confidence_info["confidence"] < 0.9:
                    confidence_info["confidence"] = min(0.95, confidence_info["confidence"] + 0.1)
                    confidence_info["level"] = "high" if confidence_info["confidence"] >= 0.8 else confidence_info["level"]
            except Exception as e:
                print(f"⚠️ Error calculating confidence for multi-step answer: {e}")
        
        # Verify multi-step answer
        verification_info = None
        if self.enable_answer_verification:
            try:
                # Use all sub-answers as context for verification
                combined_context = "\n\n".join(sub_answers)
                verification_info = self.verify_answer(query, final_answer, combined_context, sorted_sources)
            except Exception as e:
                print(f"⚠️ Error verifying multi-step answer: {e}")
                verification_info = {"status": "error", "supported": True, "details": str(e), "has_hallucinations": False}
        
        return final_answer, sorted_sources, intent_info, confidence_info, verification_info

    def classify_query_intent(self, query: str) -> dict:
        """Classify the intent of a query.
        
        Args:
            query: The user query
            
        Returns:
            Dict with 'intent' and 'confidence' keys
        """
        if not self.enable_intent_classification:
            return {"intent": "factual", "confidence": 0.5}
        
        try:
            query_lower = query.lower()
            
            # Simple keyword-based classification
            if any(word in query_lower for word in ["how to", "how do", "steps", "process", "procedure"]):
                return {"intent": "how_to", "confidence": 0.7}
            elif any(word in query_lower for word in ["what is", "what are", "define", "definition", "meaning"]):
                return {"intent": "definition", "confidence": 0.7}
            elif any(word in query_lower for word in ["compare", "difference", "versus", "vs", "similar", "different"]):
                return {"intent": "comparison", "confidence": 0.7}
            elif any(word in query_lower for word in ["list", "what are all", "enumerate", "all the"]):
                return {"intent": "list", "confidence": 0.7}
            elif any(word in query_lower for word in ["why", "explain", "how does", "how is", "reason"]):
                return {"intent": "explanation", "confidence": 0.7}
            elif any(word in query_lower for word in ["is", "are", "does", "can", "will", "verify", "confirm"]):
                return {"intent": "verification", "confidence": 0.6}
            else:
                return {"intent": "factual", "confidence": 0.5}
        except Exception as e:
            print(f"⚠️ Intent classification failed: {e}")
            return {"intent": "factual", "confidence": 0.5}

    def _load_learning_data(self):
        """Load learned patterns and strategies from file."""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.learning_data_file), exist_ok=True)
            
            if os.path.exists(self.learning_data_file):
                with open(self.learning_data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Validate structure
                    if isinstance(data, dict):
                        self.learning_data = data
                    else:
                        raise ValueError("Invalid learning data format")
            else:
                self.learning_data = {
                    "failed_queries": [],
                    "query_patterns": {},
                    "retrieval_adjustments": {},
                    "improvement_suggestions": []
                }
                # Create initial file
                self._save_learning_data()
        except Exception as e:
            print(f"⚠️ Error loading learning data: {e}")
            # Initialize with default structure
            self.learning_data = {
                "failed_queries": [],
                "query_patterns": {},
                "retrieval_adjustments": {},
                "improvement_suggestions": []
            }

    def _save_learning_data(self):
        """Save learned patterns and strategies to file."""
        try:
            os.makedirs(os.path.dirname(self.learning_data_file), exist_ok=True)
            with open(self.learning_data_file, 'w', encoding='utf-8') as f:
                json.dump(self.learning_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Error saving learning data: {e}")

    def _store_failed_query(self, query: str, answer: str, sources: List[Dict], rating: int, comment: Optional[str] = None):
        """Store information about a failed query for analysis.
        
        Args:
            query: The user query
            answer: The answer that received negative feedback
            sources: List of source citations
            rating: The feedback rating (1-5, where <=2 is negative)
            comment: Optional user comment
        """
        if not self.enable_learning_from_feedback:
            return
        
        try:
            # Ensure learning_data is initialized
            if not hasattr(self, 'learning_data') or not self.learning_data:
                self._load_learning_data()
            
            # Safely get intent
            try:
                intent = self.classify_query_intent(query).get("intent", "factual")
            except Exception:
                intent = "factual"
            
            failed_entry = {
                "query": query,
                "answer_preview": answer[:200] if answer else "",
                "sources_count": len(sources) if sources else 0,
                "sources": [s.get("source", "Unknown") for s in sources[:3]] if sources else [],  # Store top 3 sources
                "rating": rating,
                "comment": comment or "",
                "timestamp": datetime.now().isoformat(),
                "intent": intent
            }
            
            if "failed_queries" not in self.learning_data:
                self.learning_data["failed_queries"] = []
            
            self.learning_data["failed_queries"].append(failed_entry)
            
            # Keep only last 100 failed queries to avoid file bloat
            if len(self.learning_data["failed_queries"]) > 100:
                self.learning_data["failed_queries"] = self.learning_data["failed_queries"][-100:]
            
            self._save_learning_data()
            print(f"📝 Stored failed query pattern: {query[:50]}...")
            
        except Exception as e:
            print(f"⚠️ Error storing failed query: {e}")
            import traceback
            traceback.print_exc()

    def _analyze_feedback_patterns(self) -> Dict:
        """Analyze feedback patterns to identify common issues.
        
        Returns:
            Dict with analysis results including common problems and suggestions
        """
        if not self.enable_learning_from_feedback:
            return {}
        
        try:
            failed_queries = self.learning_data.get("failed_queries", [])
            if not failed_queries:
                return {"patterns": [], "common_issues": []}
            
            # Analyze common issues
            low_source_count = sum(1 for fq in failed_queries if fq.get("sources_count", 0) < 2)
            no_sources = sum(1 for fq in failed_queries if fq.get("sources_count", 0) == 0)
            
            # Group by intent
            intent_counts = Counter([fq.get("intent", "factual") for fq in failed_queries])
            
            # Extract keywords from failed queries
            all_keywords = []
            for fq in failed_queries:
                query = fq.get("query", "").lower()
                keywords = re.findall(r'\b\w{4,}\b', query)  # Words with 4+ chars
                all_keywords.extend(keywords)
            
            common_keywords = Counter(all_keywords).most_common(10)
            
            analysis = {
                "total_failures": len(failed_queries),
                "common_issues": [
                    f"Low source count ({low_source_count} queries with <2 sources)",
                    f"No sources ({no_sources} queries with 0 sources)",
                ],
                "problematic_intents": dict(intent_counts.most_common(5)),
                "common_keywords": [kw[0] for kw in common_keywords],
                "suggestions": []
            }
            
            # Generate suggestions
            if low_source_count > len(failed_queries) * 0.3:
                analysis["suggestions"].append("Consider increasing k value for retrieval")
            if no_sources > len(failed_queries) * 0.2:
                analysis["suggestions"].append("Improve query expansion for better retrieval")
            
            return analysis
            
        except Exception as e:
            print(f"⚠️ Error analyzing feedback patterns: {e}")
            return {}

    def _adjust_retrieval_strategy(self, query: str) -> Dict:
        """Adjust retrieval strategy based on learned patterns from similar failed queries.
        
        Args:
            query: The current query
            
        Returns:
            Dict with adjusted retrieval parameters
        """
        if not self.enable_learning_from_feedback:
            return {}
        
        try:
            # Check if similar queries have failed before
            similar_failures = self._get_similar_failed_queries(query)
            
            if not similar_failures:
                return {}
            
            # Analyze what went wrong
            adjustments = {}
            
            # Check if failures had low source count
            low_source_failures = [fq for fq in similar_failures if fq.get("sources_count", 0) < 2]
            if len(low_source_failures) > len(similar_failures) * 0.5:
                adjustments["k"] = 6  # Increase retrieval count
                adjustments["use_expansion"] = True  # Force query expansion
                print(f"🔧 Adjusting retrieval: increasing k to {adjustments['k']} based on past failures")
            
            # Check if failures had no sources
            no_source_failures = [fq for fq in similar_failures if fq.get("sources_count", 0) == 0]
            if len(no_source_failures) > 0:
                adjustments["k"] = max(adjustments.get("k", 4), 8)  # Even more aggressive
                adjustments["use_hybrid"] = True  # Force hybrid search
                adjustments["use_reranking"] = True  # Force re-ranking
                print(f"🔧 Adjusting retrieval: using aggressive strategy (k={adjustments['k']})")
            
            # Store adjustments for this query pattern
            query_key = query.lower().strip()[:50]  # Use first 50 chars as key
            if adjustments:
                self.learning_data["retrieval_adjustments"][query_key] = {
                    "adjustments": adjustments,
                    "last_updated": datetime.now().isoformat(),
                    "failure_count": len(similar_failures)
                }
                self._save_learning_data()
            
            return adjustments
            
        except Exception as e:
            print(f"⚠️ Error adjusting retrieval strategy: {e}")
            return {}

    def _get_similar_failed_queries(self, query: str, threshold: float = 0.3) -> List[Dict]:
        """Find similar queries that have failed in the past.
        
        Args:
            query: The current query
            threshold: Similarity threshold (0-1)
            
        Returns:
            List of similar failed query entries
        """
        if not self.enable_learning_from_feedback:
            return []
        
        try:
            failed_queries = self.learning_data.get("failed_queries", [])
            if not failed_queries:
                return []
            
            query_lower = query.lower()
            query_words = set(re.findall(r'\b\w+\b', query_lower))
            
            similar = []
            for fq in failed_queries:
                failed_query = fq.get("query", "").lower()
                failed_words = set(re.findall(r'\b\w+\b', failed_query))
                
                # Calculate simple word overlap similarity
                if query_words and failed_words:
                    overlap = len(query_words & failed_words)
                    union = len(query_words | failed_words)
                    similarity = overlap / union if union > 0 else 0
                    
                    if similarity >= threshold:
                        similar.append(fq)
            
            return similar
            
        except Exception as e:
            print(f"⚠️ Error finding similar failed queries: {e}")
            return []

    def learn_from_feedback(self, query: str, answer: str, rating: int, sources: List[Dict], comment: Optional[str] = None, feedback_type: str = "rating"):
        """Learn from user feedback to improve future retrievals.
        
        Args:
            query: The user query
            answer: The answer that was provided
            rating: Feedback rating (1-5 for stars, or -1/1 for thumbs)
            sources: List of source citations
            comment: Optional user comment
            feedback_type: Type of feedback ("rating", "thumbs", "detailed")
        """
        if not self.enable_learning_from_feedback:
            return
        
        try:
            # Ensure learning_data is initialized
            if not hasattr(self, 'learning_data') or not self.learning_data:
                self._load_learning_data()
            
            # Normalize rating based on feedback type
            normalized_rating = rating
            if feedback_type == "thumbs":
                if rating == -1:
                    normalized_rating = 1  # Thumbs down = low rating
                elif rating == 1:
                    normalized_rating = 5  # Thumbs up = high rating
            # For "rating" and "detailed" types, rating is already 1-5
            
            # Consider negative feedback as rating <= 2
            is_negative = normalized_rating <= 2
            
            if is_negative:
                print(f"📚 Learning from negative feedback (rating: {normalized_rating})")
                # Store failed query pattern
                try:
                    self._store_failed_query(query, answer, sources, normalized_rating, comment)
                except Exception as store_error:
                    print(f"⚠️ Failed to store failed query: {store_error}")
                
                # Analyze patterns (non-critical, can fail silently)
                try:
                    analysis = self._analyze_feedback_patterns()
                except Exception:
                    pass
                
                # Generate improvement suggestions using LLM (non-critical)
                if comment and len(comment.strip()) > 10:
                    try:
                        self._generate_improvement_suggestion(query, answer, comment, sources)
                    except Exception:
                        pass
                
                failed_count = len(self.learning_data.get('failed_queries', [])) if self.learning_data else 0
                print(f"✅ Learned from feedback: {failed_count} patterns stored")
            else:
                # Positive feedback - could be used to reinforce good patterns
                print(f"✅ Positive feedback received (rating: {normalized_rating})")
                
        except Exception as e:
            print(f"⚠️ Error learning from feedback: {e}")
            import traceback
            traceback.print_exc()

    def _generate_improvement_suggestion(self, query: str, answer: str, comment: str, sources: List[Dict]):
        """Generate improvement suggestions based on user comments.
        
        Args:
            query: The user query
            answer: The answer provided
            comment: User feedback comment
            sources: List of sources used
        """
        try:
            suggestion_prompt = (
                f"Query: {query}\n\n"
                f"Answer provided: {answer[:300]}...\n\n"
                f"User feedback: {comment}\n\n"
                f"Sources used: {len(sources)}\n\n"
                "Based on this feedback, suggest one specific improvement for how to better answer similar queries in the future. "
                "Be concise and actionable. Respond with only the suggestion."
            )
            
            suggestion = self._llm_chat(
                messages=[
                    {"role": "system", "content": "You are a feedback analyzer that suggests improvements."},
                    {"role": "user", "content": suggestion_prompt}
                ],
                temperature=0.3,
                max_tokens=150
            )
            if suggestion:
                self.learning_data["improvement_suggestions"].append({
                    "query": query,
                    "suggestion": suggestion,
                    "timestamp": datetime.now().isoformat()
                })
                
                # Keep only last 50 suggestions
                if len(self.learning_data["improvement_suggestions"]) > 50:
                    self.learning_data["improvement_suggestions"] = self.learning_data["improvement_suggestions"][-50:]
                
                self._save_learning_data()
                print(f"💡 Improvement suggestion: {suggestion[:80]}...")
                
        except Exception as e:
            print(f"⚠️ Error generating improvement suggestion: {e}")

    def detect_language(self, text: str) -> str:
        """Detect the language of the input text.
        
        Args:
            text: The text to detect language for
            
        Returns:
            Language code (e.g., 'en', 'es', 'fr')
        """
        if not self.enable_multilanguage or not text or len(text.strip()) < 3:
            return self.default_language
        
        try:
            # Use LLM for language detection
            detection_prompt = (
                f"Detect the language of this text and respond with ONLY the ISO 639-1 language code (e.g., 'en', 'es', 'fr', 'de', 'it', 'pt', 'zh', 'ja', 'ko', 'ar', 'ru', 'hi').\n\n"
                f"Text: {text[:200]}\n\n"
                "Language code:"
            )
            
            detected = self._llm_chat(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a language detector. Respond with only the ISO 639-1 language code."
                    },
                    {
                        "role": "user",
                        "content": detection_prompt
                    }
                ],
                temperature=0.1,
                max_tokens=5
            ).lower()
            # Clean up response (remove any extra text)
            detected = detected.split()[0] if detected.split() else self.default_language
            
            # Validate it's a supported language
            if detected in self.supported_languages:
                return detected
            else:
                return self.default_language
                
        except Exception as e:
            print(f"⚠️ Language detection failed: {e}")
            return self.default_language
    
    def translate_text(self, text: str, target_language: str, source_language: str = None) -> str:
        """Translate text to target language.
        
        Args:
            text: The text to translate
            target_language: Target language code (e.g., 'en', 'es', 'fr')
            source_language: Optional source language code (auto-detected if not provided)
            
        Returns:
            Translated text
        """
        if not self.enable_multilanguage:
            return text
        
        if target_language == self.default_language and (not source_language or source_language == self.default_language):
            return text  # No translation needed
        
        # Check cache
        cache_key = f"{source_language or 'auto'}_{target_language}_{hash(text[:100])}"
        if cache_key in self._translation_cache:
            return self._translation_cache[cache_key]
        
        try:
            # Get language names for better translation
            lang_names = {
                "en": "English", "es": "Spanish", "fr": "French", "de": "German",
                "it": "Italian", "pt": "Portuguese", "zh": "Chinese", "ja": "Japanese",
                "ko": "Korean", "ar": "Arabic", "ru": "Russian", "hi": "Hindi"
            }
            
            target_lang_name = lang_names.get(target_language, "English")
            source_lang_name = lang_names.get(source_language, "the detected language") if source_language else "the detected language"
            
            translation_prompt = (
                f"Translate the following text from {source_lang_name} to {target_lang_name}.\n\n"
                f"Text: {text}\n\n"
                f"Provide only the translation in {target_lang_name}, without any explanations or additional text."
            )
            
            translated = self._llm_chat(
                messages=[
                    {
                        "role": "system",
                        "content": f"You are a professional translator. Translate accurately and naturally to {target_lang_name}."
                    },
                    {
                        "role": "user",
                        "content": translation_prompt
                    }
                ],
                temperature=0.3,
                max_tokens=len(text) * 2
            )
            
            # Clean up translation (remove quotes if present)
            if translated.startswith('"') and translated.endswith('"'):
                translated = translated[1:-1]
            if translated.startswith("'") and translated.endswith("'"):
                translated = translated[1:-1]
            
            # Cache the translation
            self._translation_cache[cache_key] = translated
            # Limit cache size
            if len(self._translation_cache) > 1000:
                # Remove oldest entries (simple FIFO)
                keys_to_remove = list(self._translation_cache.keys())[:200]
                for key in keys_to_remove:
                    del self._translation_cache[key]
            
            return translated
            
        except Exception as e:
            print(f"⚠️ Translation failed: {e}")
            return text  # Return original on error

    def ask_question(self, query, document_filters=None, conversation_context=None, advanced_filters=None, user_language: str = None):
        """Ask a question and return answer with source citations.
        
        Args:
            query: The question to ask
            document_filters: Optional list of document filenames to filter by (legacy)
            conversation_context: Optional list of previous messages for context
            advanced_filters: Optional AdvancedSearchFilters object for advanced filtering
            user_language: Optional user's preferred language code (auto-detected if not provided)
        """
        # Quick validation
        if not query or not query.strip():
            confidence_info = {"confidence": 0.0, "level": "very_low", "factors": {}} if self.enable_confidence_scoring else None
            verification_info = {"status": "not_verified", "supported": False, "details": "Invalid query", "has_hallucinations": False} if self.enable_answer_verification else None
            return "Please provide a valid question.", [], {"intent": "factual", "confidence": 0.0}, confidence_info, verification_info
        
        # Check cache first (if enabled and not a follow-up question)
        cache_key = None
        if self.enable_query_caching and self.query_cache and not conversation_context:
            # Generate cache key
            advanced_filters_dict = None
            if advanced_filters:
                advanced_filters_dict = {
                    "date_from": advanced_filters.date_from.isoformat() if advanced_filters.date_from else None,
                    "date_to": advanced_filters.date_to.isoformat() if advanced_filters.date_to else None,
                    "min_relevance": advanced_filters.min_relevance,
                    "max_results": advanced_filters.max_results,
                    "exclude_documents": advanced_filters.exclude_documents
                }
            
            cache_key = self.query_cache._generate_cache_key(
                query, 
                document_filters, 
                advanced_filters_dict,
                user_language
            )
            
            # Try to get from cache
            cached_result = self.query_cache.get(cache_key)
            if cached_result:
                print(f"⚡ Cache HIT for query: {query[:50]}...")
                # Record analytics for cache hit (with minimal data)
                try:
                    from .analytics import AnalyticsTracker
                    AnalyticsTracker.record_query_analytics(
                        query=query,
                        response_time=0.01,  # Cache hits are very fast
                        sources=cached_result.get('sources', []),
                        intent=cached_result.get('intent_info', {}).get('intent') if cached_result.get('intent_info') else None,
                        confidence=cached_result.get('confidence_info', {}).get('confidence') if cached_result.get('confidence_info') else None,
                        verification_status=cached_result.get('verification_info', {}).get('status') if cached_result.get('verification_info') else None,
                        cache_hit=True,  # Mark as cache hit
                        user_id=None
                    )
                except Exception as e:
                    print(f"⚠️ Failed to record cache hit analytics: {e}")
                
                return (
                    cached_result['answer'],
                    cached_result['sources'],
                    cached_result.get('intent_info', {}),
                    cached_result.get('confidence_info'),
                    cached_result.get('verification_info')
                )
            else:
                print(f"💾 Cache MISS for query: {query[:50]}...")
        
        # Multi-language support: detect and translate query if needed
        detected_language = self.default_language
        original_query = query
        query_for_processing = query
        
        if self.enable_multilanguage:
            # Detect language if not provided
            if user_language:
                detected_language = user_language if user_language in self.supported_languages else self.default_language
            else:
                detected_language = self.detect_language(query)
            
            # Translate query to English for processing (since embeddings are English-based)
            if detected_language != self.default_language:
                query_for_processing = self.translate_text(query, self.default_language, detected_language)
                print(f"🌐 Detected language: {detected_language}, translated query for processing")
        
        # Classify query intent
        intent_info = self.classify_query_intent(query)
        intent_type = intent_info.get("intent", "factual")
        
        # Check if knowledge base has any documents
        try:
            kb_count = self.processor.collection.count()
            if kb_count == 0:
                return "⚠️ Knowledge base is empty. Please upload documents first. Documents are processed in the background - wait a few seconds after uploading and try again.", [], intent_info
        except Exception as e:
            return f"⚠️ Error accessing knowledge base: {str(e)}", [], intent_info
        
        # If document filters are specified, validate they exist
        if document_filters:
            try:
                # Get all available documents
                all_docs = self.processor.list_documents()
                available_doc_names = {doc.get("filename") for doc in all_docs}
                
                # Filter out invalid document names
                valid_filters = [f for f in document_filters if f in available_doc_names]
                
                if not valid_filters:
                    confidence_info = {"confidence": 0.0, "level": "very_low", "factors": {}} if self.enable_confidence_scoring else None
                    verification_info = {"status": "not_verified", "supported": False, "details": "Invalid document filters", "has_hallucinations": False} if self.enable_answer_verification else None
                    return f"⚠️ None of the selected documents exist in the knowledge base. Available documents: {', '.join(list(available_doc_names)[:5])}", [], intent_info, confidence_info, verification_info
                
                # Use only valid filters
                document_filters = valid_filters
            except Exception as e:
                print(f"⚠️ Error validating document filters: {e}")
                # Continue without filters if validation fails
        
        # Check for similar failed queries and adjust retrieval strategy
        retrieval_adjustments = {}
        if self.enable_learning_from_feedback:
            retrieval_adjustments = self._adjust_retrieval_strategy(query)
        
        # Check if query requires multi-step reasoning
        if self.enable_multi_step_reasoning and self._is_complex_query(query, intent_info):
            try:
                return self.multi_step_reasoning(
                    query,
                    document_filters=document_filters,
                    advanced_filters=advanced_filters,
                    conversation_context=conversation_context
                )
            except Exception as e:
                print(f"⚠️ Multi-step reasoning failed: {e}, falling back to standard reasoning")
                # Fall through to standard reasoning
        
        # Adjust retrieval parameters based on intent
        k_value = 4  # Default
        if intent_type == "list":
            k_value = 6  # Need more chunks for comprehensive lists
        elif intent_type == "comparison":
            k_value = 6  # Need more chunks to compare multiple things
        elif intent_type == "explanation":
            k_value = 5  # Need more context for explanations
        elif intent_type == "definition":
            k_value = 3  # Definitions usually need less context
        elif intent_type == "verification":
            k_value = 3  # Verification questions need focused context
        
        # Apply learned retrieval adjustments from feedback
        if retrieval_adjustments and "k" in retrieval_adjustments:
            k_value = max(k_value, retrieval_adjustments["k"])  # Use higher k if learned
            print(f"📚 Applied learned adjustment: k={k_value}")
        
        # Detect if this is a follow-up question
        is_followup = bool(conversation_context and len(conversation_context) > 0)
        
        # Enhance query for follow-up questions
        enhanced_query = query
        if is_followup:
            # Extract key information from previous conversation for context
            previous_context_summary = self._extract_conversation_summary(conversation_context)
            if previous_context_summary:
                # Enhance query with conversation context
                enhanced_query = f"{query}\n\n[Previous conversation context: {previous_context_summary}]"
        
        # Add conversation context to chat history if provided
        if conversation_context:
            # Add conversation messages to history (excluding system message)
            # Limit to last 6 messages (3 exchanges) to avoid token bloat
            recent_context = conversation_context[-6:] if len(conversation_context) > 6 else conversation_context
            for msg in recent_context:
                if msg.get("role") in ["user", "assistant"]:
                    self.chat_history.append({
                        "role": msg.get("role"),
                        "content": msg.get("content", "")
                    })
        
        # Retrieve context with sources and filters (use enhanced query for better retrieval)
        context, sources = self.retrieve_context(
            enhanced_query if is_followup else query, 
            k=k_value,  # Use intent-adjusted k value
            document_filters=document_filters,
            advanced_filters=advanced_filters
        )

        if not context:
            context = ""
        
        # Generate response with follow-up awareness and intent guidance
        # Use original query for response generation to maintain context
        try:
            response = self.generate_response(query_for_processing, context, is_followup=is_followup, intent=intent_info)
            
            # Calculate confidence score
            confidence_info = None
            if self.enable_confidence_scoring:
                confidence_info = self.score_answer_confidence(query, response, context, sources)
            
            # Verify answer is supported by context
            verification_info = None
            if self.enable_answer_verification:
                verification_info = self.verify_answer(query_for_processing, response, context, sources)
                # Log verification results
                if verification_info.get("status") != "supported":
                    print(f"⚠️ Answer verification: {verification_info.get('status')} - {verification_info.get('details', '')[:100]}")
            
            # Translate answer back to user's language if needed
            final_response = response
            if self.enable_multilanguage and detected_language != self.default_language:
                final_response = self.translate_text(response, detected_language, self.default_language)
                print(f"🌐 Translated answer to {detected_language}")
            
            # Store in cache if enabled and not a follow-up question.
            # Never cache transport/LLM failure strings.
            if (
                self.enable_query_caching
                and self.query_cache
                and cache_key
                and not conversation_context
                and final_response
                and not str(final_response).lstrip().startswith("❌ Error")
            ):
                self.query_cache.set(
                    cache_key,
                    final_response,
                    sources,
                    intent_info,
                    confidence_info,
                    verification_info
                )
                print(f"💾 Cached result for query: {query[:50]}...")
            
            # Return response with sources, intent, confidence, and verification
            return final_response, sources, intent_info, confidence_info, verification_info
        except Exception as e:
            verification_info = {"status": "error", "supported": True, "details": str(e), "has_hallucinations": False} if self.enable_answer_verification else None
            return f"❌ Error: {str(e)}", [], intent_info, None, verification_info
    
    def _extract_conversation_summary(self, conversation_context: list) -> str:
        """Extract a concise summary of previous conversation for context enhancement."""
        if not conversation_context:
            return ""
        
        # Get last few exchanges
        recent = conversation_context[-4:] if len(conversation_context) > 4 else conversation_context
        
        summary_parts = []
        for msg in recent:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                summary_parts.append(f"User asked: {content[:100]}")
            elif role == "assistant":
                summary_parts.append(f"Assistant answered: {content[:150]}")
        
        return " | ".join(summary_parts) if summary_parts else ""

    def verify_answer(self, query: str, answer: str, context: str, sources: List[Dict]) -> Dict:
        """Verify if answer is fully supported by the provided context.
        
        Uses LLM to check if the answer:
        1. Is fully supported by the context
        2. Contains information not in the context (hallucinations)
        3. Has any contradictions with the context
        
        Args:
            query: The user's query
            answer: The generated answer
            context: The context used to generate the answer
            sources: List of source citations
            
        Returns:
            Dictionary with verification status and details
        """
        if not self.enable_answer_verification:
            return {"status": "not_verified", "supported": True, "details": "Verification disabled", "has_hallucinations": False}
        
        try:
            # Limit context length for verification prompt (use first portion if very long)
            context_for_verification = context[:2000] if len(context) > 2000 else context
            if len(context) > 2000:
                context_for_verification += "\n\n[... additional context truncated ...]"
            
            verification_prompt = (
                f"Question: {query}\n\n"
                f"Answer provided: {answer}\n\n"
                f"Context used to generate answer:\n{context_for_verification}\n\n"
                "Analyze if this answer is:\n"
                "1. FULLY SUPPORTED - All information in the answer is present in the context\n"
                "2. PARTIALLY SUPPORTED - Some information is in context, but answer contains additional unsupported claims\n"
                "3. UNSUPPORTED - Answer contains information not found in the context or contradicts the context\n\n"
                "Respond with ONLY one of these three words: SUPPORTED, PARTIAL, or UNSUPPORTED\n"
                "Then on a new line, provide a brief explanation (1-2 sentences)."
            )
            
            verification_text = self._llm_chat(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a fact-checker. Verify if answers are supported by provided context. Respond with SUPPORTED, PARTIAL, or UNSUPPORTED followed by a brief explanation."
                    },
                    {
                        "role": "user",
                        "content": verification_prompt
                    }
                ],
                temperature=0.1,
                max_tokens=200
            )
            
            # Parse verification result
            verification_upper = verification_text.upper()
            if "SUPPORTED" in verification_upper and "PARTIAL" not in verification_upper and "UNSUPPORTED" not in verification_upper:
                status = "supported"
                supported = True
            elif "UNSUPPORTED" in verification_upper:
                status = "unsupported"
                supported = False
            elif "PARTIAL" in verification_upper:
                status = "partial"
                supported = False  # Partial support means some unsupported claims
            else:
                # Default to supported if unclear
                status = "supported"
                supported = True
            
            # Extract explanation (everything after the status word)
            explanation = verification_text
            for word in ["SUPPORTED", "PARTIAL", "UNSUPPORTED"]:
                if word in verification_upper:
                    # Get text after the status word
                    parts = verification_text.split(word, 1)
                    if len(parts) > 1:
                        explanation = parts[1].strip()
                        break
            
            # Clean up explanation
            explanation = explanation.lstrip(":.,- ").strip()
            if not explanation or len(explanation) < 10:
                if status == "supported":
                    explanation = "Answer is fully supported by the provided context."
                elif status == "partial":
                    explanation = "Answer contains some information not fully supported by the context."
                else:
                    explanation = "Answer contains information not found in or contradicts the provided context."
            
            return {
                "status": status,
                "supported": supported,
                "details": explanation,
                "has_hallucinations": not supported
            }
            
        except Exception as e:
            print(f"⚠️ Answer verification failed: {e}")
            # On error, assume supported to avoid blocking answers
            return {
                "status": "error",
                "supported": True,
                "details": f"Verification error: {str(e)}",
                "has_hallucinations": False
            }

    def _calculate_avg_relevance(self, sources: List[Dict]) -> float:
        """Calculate average relevance score from sources.
        
        Args:
            sources: List of source citation dictionaries
            
        Returns:
            Average relevance score (0.0-1.0)
        """
        if not sources:
            return 0.0
        
        relevance_scores = [s.get("relevance", 0.0) for s in sources if s]
        if not relevance_scores:
            return 0.0
        
        return sum(relevance_scores) / len(relevance_scores)

    def _assess_answer_completeness(self, query: str, answer: str) -> float:
        """Assess how completely the answer addresses the query.
        
        Args:
            query: The user's query
            answer: The generated answer
            
        Returns:
            Completeness score (0.0-1.0)
        """
        if not query or not answer:
            return 0.0
        
        query_lower = query.lower()
        answer_lower = answer.lower()
        
        # Extract key terms from query
        query_terms = set(re.findall(r'\b\w{4,}\b', query_lower))  # Words with 4+ chars
        
        if not query_terms:
            # If no meaningful terms, check if answer is substantial
            return min(1.0, len(answer) / 100.0)  # Normalize by length
        
        # Check how many query terms appear in answer
        matched_terms = sum(1 for term in query_terms if term in answer_lower)
        term_coverage = matched_terms / len(query_terms) if query_terms else 0.0
        
        # Check answer length (too short = incomplete, too long might be verbose)
        # Optimal answer length is roughly 50-500 chars for most queries
        length_score = 1.0
        if len(answer) < 50:
            length_score = len(answer) / 50.0  # Penalize very short answers
        elif len(answer) > 1000:
            length_score = 0.9  # Slight penalty for very long answers
        
        # Combine term coverage and length
        completeness = (term_coverage * 0.7 + length_score * 0.3)
        return min(1.0, completeness)

    def score_answer_confidence(self, query: str, answer: str, context: str, sources: List[Dict]) -> Dict:
        """Calculate confidence score for an answer.
        
        Args:
            query: The user's query
            answer: The generated answer
            context: The context used to generate the answer
            sources: List of source citations
            
        Returns:
            Dictionary with confidence score and breakdown of factors
        """
        if not self.enable_confidence_scoring:
            return {"confidence": 0.5, "factors": {}}
        
        try:
            # Factor 1: Source relevance (40% weight)
            # Higher relevance = more confidence
            avg_relevance = self._calculate_avg_relevance(sources)
            source_relevance_score = avg_relevance
            
            # Factor 2: Context coverage (30% weight)
            # More context = potentially better answer
            context_coverage = min(1.0, len(context) / self.max_context_chars) if context else 0.0
            # Bonus if context is substantial but not excessive
            if 0.3 <= context_coverage <= 0.9:
                context_coverage_score = 1.0
            else:
                context_coverage_score = context_coverage
            
            # Factor 3: Source count (15% weight)
            # More sources = more confidence (up to a point)
            source_count = len(sources) if sources else 0
            source_count_score = min(1.0, source_count / 3.0)  # Optimal at 3+ sources
            
            # Factor 4: Answer completeness (15% weight)
            # How well the answer addresses the query
            completeness_score = self._assess_answer_completeness(query, answer)
            
            # Calculate weighted confidence score
            confidence = (
                source_relevance_score * 0.40 +
                context_coverage_score * 0.30 +
                source_count_score * 0.15 +
                completeness_score * 0.15
            )
            
            # Round to 2 decimal places
            confidence = round(confidence, 2)
            
            # Determine confidence level
            if confidence >= 0.8:
                level = "high"
            elif confidence >= 0.6:
                level = "medium"
            elif confidence >= 0.4:
                level = "low"
            else:
                level = "very_low"
            
            return {
                "confidence": confidence,
                "level": level,
                "factors": {
                    "source_relevance": round(source_relevance_score, 2),
                    "context_coverage": round(context_coverage_score, 2),
                    "source_count": source_count,
                    "source_count_score": round(source_count_score, 2),
                    "answer_completeness": round(completeness_score, 2)
                }
            }
            
        except Exception as e:
            print(f"⚠️ Error calculating confidence score: {e}")
            return {"confidence": 0.5, "level": "unknown", "factors": {}}
    
    def generate_document_suggestions(self, limit: int = 10, force_refresh: bool = False) -> List[Dict]:
        """Generate query suggestions based on document content in the knowledge base.
        
        This method:
        1. Samples diverse chunks from the knowledge base
        2. Extracts key topics and concepts
        3. Uses LLM to generate natural, relevant questions
        4. Caches results for performance
        
        Args:
            limit: Maximum number of suggestions to return
            force_refresh: If True, bypass cache and regenerate suggestions
            
        Returns:
            List of suggestion dictionaries with 'query', 'type', 'score', and 'source'
        """
        # Check cache first
        if not force_refresh and self._document_suggestions_cache is not None:
            import time
            if self._document_suggestions_cache_time and \
               (time.time() - self._document_suggestions_cache_time) < self._document_suggestions_cache_ttl:
                return self._document_suggestions_cache[:limit]
        
        try:
            # Check if knowledge base has content
            total_chunks = self.processor.collection.count()
            if total_chunks == 0:
                return []
            
            # Sample diverse chunks from the knowledge base
            # Get chunks from different documents to ensure diversity
            sample_size = min(50, total_chunks)  # Sample up to 50 chunks
            
            try:
                # Get a diverse sample of chunks
                all_results = self.processor.collection.get(
                    limit=sample_size,
                    include=['documents', 'metadatas']
                )
            except Exception as e:
                print(f"⚠️ Error sampling chunks for suggestions: {e}")
                return []
            
            if not all_results or not all_results.get('documents'):
                return []
            
            documents = all_results.get('documents', [])
            metadatas = all_results.get('metadatas', [])
            
            # Group chunks by document to ensure diversity
            doc_chunks = {}
            for i, (doc, meta) in enumerate(zip(documents, metadatas)):
                source = meta.get('source', 'unknown') if meta else 'unknown'
                if source not in doc_chunks:
                    doc_chunks[source] = []
                # Limit chunks per document to ensure diversity
                if len(doc_chunks[source]) < 5:
                    doc_chunks[source].append(doc[:500])  # Use first 500 chars per chunk
            
            # Combine chunks from different documents
            diverse_chunks = []
            for source, chunks in doc_chunks.items():
                diverse_chunks.extend(chunks[:3])  # Max 3 chunks per document
            
            if not diverse_chunks:
                return []
            
            # Create a summary of content for LLM
            content_summary = "\n\n---\n\n".join(diverse_chunks[:20])  # Use up to 20 chunks
            if len(content_summary) > 3000:
                content_summary = content_summary[:3000] + "..."
            
            # Use LLM to generate questions based on content
            suggestion_prompt = (
                f"Based on the following content from a knowledge base, generate {limit} diverse, "
                f"natural questions that users might ask about this content.\n\n"
                f"Content samples:\n{content_summary}\n\n"
                "Requirements:\n"
                "1. Questions should be natural and conversational\n"
                "2. Cover different topics and aspects\n"
                "3. Include various question types (what, how, why, when, where, who)\n"
                "4. Questions should be answerable from the provided content\n"
                "5. Make questions specific and actionable\n\n"
                "Generate exactly {limit} questions, one per line, without numbering or bullets."
            ).format(limit=limit)
            
            try:
                suggestions_text = self._llm_chat(
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a query suggestion generator. Create natural, diverse questions based on document content."
                        },
                        {
                            "role": "user",
                            "content": suggestion_prompt
                        }
                    ],
                    temperature=0.7,
                    max_tokens=limit * 50
                )
                
                # Parse suggestions (one per line)
                suggestions = []
                for line in suggestions_text.split('\n'):
                    line = line.strip()
                    # Remove numbering, bullets, dashes
                    line = re.sub(r'^[\d\.\-\*\•\)\s]+', '', line)
                    line = line.strip()
                    
                    # Validate question
                    if line and len(line) > 10 and len(line) < 200:
                        # Check if it looks like a question
                        if any(line.strip().startswith(qword) for qword in ['What', 'How', 'Why', 'When', 'Where', 'Who', 'Which', 'Can', 'Should', 'Is', 'Are', 'Does', 'Do']):
                            suggestions.append({
                                "query": line,
                                "type": "document",
                                "score": 0.9,  # High score for document-based suggestions
                                "source": "knowledge_base"
                            })
                        elif '?' in line:
                            # Also accept questions ending with ?
                            suggestions.append({
                                "query": line,
                                "type": "document",
                                "score": 0.85,
                                "source": "knowledge_base"
                            })
                
                # If we got fewer suggestions than requested, try to generate more
                if len(suggestions) < limit and len(diverse_chunks) > 10:
                    # Try with more chunks
                    additional_content = "\n\n---\n\n".join(diverse_chunks[10:30])
                    if len(additional_content) > 2000:
                        additional_content = additional_content[:2000] + "..."
                    
                    additional_prompt = (
                        f"Generate {limit - len(suggestions)} more diverse questions based on this additional content:\n\n"
                        f"{additional_content}\n\n"
                        "Generate natural questions, one per line."
                    )
                    
                    try:
                        additional_text = self._llm_chat(
                            messages=[
                                {"role": "user", "content": additional_prompt}
                            ],
                            temperature=0.7,
                            max_tokens=(limit - len(suggestions)) * 50
                        )
                        for line in additional_text.split('\n'):
                            line = re.sub(r'^[\d\.\-\*\•\)\s]+', '', line.strip())
                            if line and len(line) > 10 and len(line) < 200 and line not in [s["query"] for s in suggestions]:
                                if '?' in line or any(line.strip().startswith(qword) for qword in ['What', 'How', 'Why', 'When', 'Where', 'Who', 'Which', 'Can', 'Should', 'Is', 'Are']):
                                    suggestions.append({
                                        "query": line,
                                        "type": "document",
                                        "score": 0.8,
                                        "source": "knowledge_base"
                                    })
                                if len(suggestions) >= limit:
                                    break
                    except Exception as e:
                        print(f"⚠️ Error generating additional suggestions: {e}")
                
                # Cache the results
                import time
                self._document_suggestions_cache = suggestions[:limit]
                self._document_suggestions_cache_time = time.time()
                
                return suggestions[:limit]
                
            except Exception as e:
                print(f"⚠️ Error generating document suggestions: {e}")
                return []
                
        except Exception as e:
            print(f"⚠️ Error in generate_document_suggestions: {e}")
            import traceback
            traceback.print_exc()
            return []
