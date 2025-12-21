# Memory Optimization for Railway Deployment

## Problem
Railway deployment crashed with "out of memory" error. The application was consuming too much memory in the production environment.

## Root Causes

1. **Large Query Cache**: Cache was set to 1000 entries, consuming significant memory
2. **Multiple LLM Calls**: Features like reranking, verification, intent classification each make additional Ollama API calls that accumulate in memory
3. **Context Size**: Large context windows (2500 chars) use more memory per request
4. **ChromaDB**: Vector database can grow and consume memory as documents are added
5. **Embedding Models**: Sentence transformer models load into memory (~80MB for all-MiniLM-L6-v2)

## Optimizations Applied

### 1. Reduced Cache Sizes (`src/dependencies.py`)

**Before:**
- `cache_max_size=1000` (1000 cached queries)
- `cache_ttl=3600` (1 hour cache)

**After:**
- `cache_max_size=100` (100 cached queries) - **90% reduction**
- `cache_ttl=1800` (30 minutes cache) - **50% reduction**

### 2. Disabled Memory-Intensive Features

**Disabled (each makes additional LLM calls):**
- `enable_reranking=False` - Re-ranking requires LLM calls for top chunks
- `enable_intent_classification=False` - Additional LLM call per query
- `enable_multi_step_reasoning=False` - Multiple LLM calls for complex queries
- `enable_context_summarization=False` - Additional LLM call for long contexts
- `enable_answer_verification=False` - Additional LLM call per answer

**Kept (low memory impact):**
- `enable_streaming=True` - Actually reduces memory by streaming responses
- `enable_query_expansion=True` - Single LLM call, cached
- `enable_hybrid_search=True` - No additional memory overhead
- `enable_learning_from_feedback=True` - Minimal memory impact
- `enable_confidence_scoring=True` - Heuristic-based, no LLM calls
- `enable_query_caching=True` - Reduces redundant queries (with smaller cache)

### 3. Reduced Context Size

**Before:**
- `max_context_chars=2500`

**After:**
- `max_context_chars=2000` - **20% reduction**

### 4. LLM Model Optimization

**Before:**
- Using `mistral` model (~4.1GB RAM when loaded by Ollama)

**After:**
- Using `phi3:mini` model (~2.3GB RAM) - **44% memory reduction**
- Configurable via `LLM_MODEL` environment variable
- Better performance on RAG tasks despite smaller size

**Available Models (via `LLM_MODEL` environment variable):**
- `phi3:mini` (3.8B params, ~2.3GB RAM) - **Recommended default**: Excellent quality-to-size ratio, fast inference, optimized for RAG
- `llama3.2:3b` (3B params, ~2GB RAM) - Very efficient, good performance
- `gemma2:2b` (2B params, ~1.5GB RAM) - Smallest option, decent quality
- `qwen2.5:3b` (3B params, ~2GB RAM) - Good multilingual support
- `mistral` (7B params, ~4.1GB RAM) - Larger, more memory-intensive

**Note:** Make sure your Ollama instance has the selected model pulled. Run `ollama pull phi3:mini` (or your chosen model) on your Ollama server.

### 5. Environment Variable Optimizations (`nixpacks.toml`)

Added memory-related environment variables:
- `PYTHONHASHSEED=0` - Reduces memory fragmentation
- `CHROMA_CACHE_SIZE=100` - Limits ChromaDB cache size
- `MALLOC_TRIM_THRESHOLD_=65536` - Helps Python release memory back to OS
- `LLM_MODEL=phi-3-mini` - Configurable LLM model selection

## Expected Memory Reduction

- **Query Cache**: ~90% reduction (from 1000 to 100 entries)
- **LLM Calls**: ~60% reduction (disabled 5 memory-intensive features)
- **Context Memory**: ~20% reduction (from 2500 to 2000 chars)
- **LLM Model**: ~44% reduction (from mistral 4.1GB to phi-3-mini 2.3GB)
- **Total Estimated Reduction**: **60-75% less memory usage**

## Railway Memory Limits

- **Free Tier**: ~512MB-1GB (varies)
- **Pro Tier**: 2GB+ (configurable)

If still hitting limits on free tier, consider:
1. Upgrading Railway plan
2. Further reducing `cache_max_size` to 50
3. Reducing `max_context_chars` to 1500
4. Using a smaller LLM model (e.g., `gemma2:2b` for ~1.5GB RAM)
5. Using external Ollama service (separate from Railway deployment)

## Monitoring

Check Railway dashboard for:
- Memory usage metrics
- Crash logs (look for OOM - Out Of Memory errors)
- Request patterns (high traffic = higher memory)

## Reverting Optimizations

If you need to re-enable features, you can modify `src/dependencies.py`:

```python
assistant = KnowledgeAssistant(
    processor,
    model_name="mistral",
    # Re-enable features one at a time, monitor memory usage
    enable_reranking=True,  # Re-enable if you have enough memory
    enable_answer_verification=True,
    # etc.
)
```

**Note:** Only re-enable features if you've upgraded Railway plan or confirmed you have sufficient memory.

## Additional Tips

1. **Monitor Memory Usage**: Use Railway's metrics dashboard to track memory over time
2. **Scale Gradually**: Re-enable features one at a time and monitor impact
3. **Use External Ollama**: If running Ollama locally, consider using an external service to offload LLM processing
4. **Regular Cleanup**: The smaller cache will auto-clean more frequently, helping prevent memory leaks

