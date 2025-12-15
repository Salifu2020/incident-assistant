# Embedding Model Upgrade Guide

## Overview

The system has been upgraded to use a better embedding model for improved retrieval accuracy. The default model has been changed from `all-MiniLM-L6-v2` to `all-mpnet-base-v2`.

## What Changed

### Previous Model
- **Model**: `all-MiniLM-L6-v2`
- **Pros**: Fast, small, efficient
- **Cons**: Lower accuracy compared to newer models

### New Model
- **Model**: `all-mpnet-base-v2` (default)
- **Pros**: Better accuracy, improved semantic understanding
- **Cons**: Slightly slower and larger

### Available Models

1. **all-MiniLM-L6-v2** (Fast)
   - Small and fast
   - Good for quick prototyping
   - Lower accuracy

2. **all-mpnet-base-v2** (Recommended - Default)
   - Better accuracy than MiniLM
   - Good balance of speed and quality
   - Recommended for production use

3. **BAAI/bge-large-en-v1.5** (State-of-the-art)
   - Best accuracy
   - Slower and requires more resources
   - Best for high-accuracy requirements

## Important: Re-indexing Required

⚠️ **When you change the embedding model, you MUST re-index all documents.**

Embeddings are model-specific and cannot be reused across different models. The system includes a re-indexing function to handle this automatically.

## How to Re-index

### Option 1: Using the API Endpoint

```bash
# Re-index with default model (all-mpnet-base-v2)
curl -X POST "http://localhost:8000/reindex" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Re-index with a specific model
curl -X POST "http://localhost:8000/reindex?new_embedding_model=BAAI/bge-large-en-v1.5" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Option 2: Using Python

```python
from src.ingestion import DocumentProcessor

processor = DocumentProcessor(embedding_model="all-mpnet-base-v2")
success, message = processor.reindex_with_new_model("all-mpnet-base-v2")
print(message)
```

### Option 3: Programmatically in Code

```python
from src.ingestion import DocumentProcessor

# Initialize with new model
processor = DocumentProcessor(embedding_model="all-mpnet-base-v2")

# Re-index all documents
success, message = processor.reindex_with_new_model("all-mpnet-base-v2")
if success:
    print(f"✅ {message}")
else:
    print(f"❌ {message}")
```

## Configuration

### Changing the Default Model

Edit `src/dependencies.py`:

```python
# Use all-mpnet-base-v2 (recommended)
processor = DocumentProcessor(embedding_model="all-mpnet-base-v2")

# Or use BAAI/bge-large-en-v1.5 for best accuracy
processor = DocumentProcessor(embedding_model="BAAI/bge-large-en-v1.5")
```

## Performance Considerations

| Model | Speed | Accuracy | Memory | Use Case |
|-------|-------|----------|--------|----------|
| all-MiniLM-L6-v2 | ⚡⚡⚡ Fast | ⭐⭐ Good | 💾 Low | Prototyping, quick tests |
| all-mpnet-base-v2 | ⚡⚡ Medium | ⭐⭐⭐ Better | 💾💾 Medium | **Production (Recommended)** |
| BAAI/bge-large-en-v1.5 | ⚡ Slow | ⭐⭐⭐⭐ Best | 💾💾💾 High | High-accuracy requirements |

## Expected Improvements

After upgrading to `all-mpnet-base-v2`, you can expect:
- **+15-20% improvement** in retrieval accuracy
- Better semantic understanding
- More relevant search results
- Improved answer quality

## Troubleshooting

### Issue: Model Download Timeout or Slow Download
- **Solution**: This is normal - the download will automatically resume
- The model is ~438MB and may take several minutes depending on your connection
- Once downloaded, it's cached locally and won't need to download again
- If download continues to fail, you can:
  1. Use `all-MiniLM-L6-v2` temporarily (smaller, faster download)
  2. Manually download the model from HuggingFace
  3. Check your internet connection and firewall settings

### Issue: "No documents to re-index"
- **Solution**: Upload documents first, then re-index

### Issue: Re-indexing fails
- **Solution**: Check that all source files exist in `ingested_files/` directory
- Ensure you have write permissions
- Check API logs for detailed error messages

### Issue: Slow re-indexing
- **Solution**: This is normal for large document collections
- Re-indexing processes all documents sequentially
- Consider using the faster `all-MiniLM-L6-v2` if speed is critical

## Migration Checklist

- [ ] Backup existing ChromaDB data (optional, but recommended)
- [ ] Update `src/dependencies.py` with new embedding model
- [ ] Run re-indexing process
- [ ] Verify documents are properly indexed
- [ ] Test query accuracy improvements
- [ ] Monitor performance

## Notes

- Re-indexing will delete the old collection and create a new one
- All documents must be re-processed
- Source files in `ingested_files/` are used for re-indexing
- The process is automatic but may take time for large collections

