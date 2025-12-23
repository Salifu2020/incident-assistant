# Alternative Deployment Solutions - Free Tier Options

Since Railway's free tier is hitting memory limits, here are better alternatives that don't require premium subscriptions.

## 🎯 Recommended: Render (Best Free Tier for Python)

**Why Render is Better:**
- **512MB RAM** (more flexible than Railway)
- Better memory management for Python apps
- 750 hours/month free (enough for 24/7)
- Automatic deployments from GitHub
- Similar to Railway in ease of use

### Quick Migration to Render:

1. **Sign up**: https://render.com (free)
2. **Create Web Service**:
   - Click "New" → "Web Service"
   - Connect your GitHub repository
   - Select `incident-assistant` repo
3. **Configure**:
   - **Name**: `incident-assistant-api`
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python run_api.py`
   - **Plan**: Free
4. **Environment Variables**:
   - `SECRET_KEY=your-secret-key`
   - `OLLAMA_HOST=https://your-ollama-url` (from Railway fearless-prosperity)
   - `EMBEDDING_MODEL=all-MiniLM-L6-v2`
   - `LLM_MODEL=phi3:mini`
   - `PORT=10000` (Render auto-sets this, but good to have)
5. **Deploy**: Render will auto-deploy
6. **Update Streamlit**: Update `API_URL` in Streamlit Cloud secrets

**Advantages:**
- Better memory handling
- Free tier more generous
- Easy migration
- No code changes needed

---

## 🚀 Alternative: Fly.io (Very Flexible)

**Why Fly.io:**
- **256MB RAM per app** (can run multiple apps)
- Very flexible - run many small services
- Great for microservices
- Free tier: 3 shared-cpu VMs

### Setup on Fly.io:

1. **Install Fly CLI**: 
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```

2. **Login**:
   ```bash
   flyctl auth login
   ```

3. **Create app**:
   ```bash
   cd /path/to/incident-assistant
   flyctl launch
   ```
   - This creates `fly.toml`

4. **Set secrets**:
   ```bash
   flyctl secrets set SECRET_KEY=your-secret-key
   flyctl secrets set OLLAMA_HOST=https://your-ollama-url
   flyctl secrets set EMBEDDING_MODEL=all-MiniLM-L6-v2
   flyctl secrets set LLM_MODEL=phi3:mini
   ```

5. **Deploy**:
   ```bash
   flyctl deploy
   ```

**Advantages:**
- Very flexible memory allocation
- Can run multiple services separately
- Excellent for separating API and processing

---

## 💡 Alternative: Further Optimize Current Setup

Before switching, try these **ultra-aggressive optimizations**:

### Option A: Disable Query Caching Entirely

In `src/dependencies.py`, change:
```python
enable_query_caching=False,  # Disable entirely
# Remove cache_max_size and cache_ttl (won't be used)
```

This saves ~10-50MB.

### Option B: Reduce Context Size Further

```python
max_context_chars=1500,  # Reduce from 2000 to 1500
```

### Option C: Disable All Optional Features

```python
enable_query_expansion=False,  # Disable
enable_hybrid_search=False,  # Disable (uses more memory)
enable_confidence_scoring=False,  # Disable
```

### Option D: Use Even Smaller Embedding Model

Change `EMBEDDING_MODEL` in Railway variables:
- `paraphrase-MiniLM-L3-v2` (~40MB instead of 80MB)
- Or `all-MiniLM-L6-v2` (current, ~80MB)

---

## 🔧 Alternative: External Services (Zero Memory)

Offload heavy components to external services (free/cheap tiers):

### 1. Use Pinecone for Vector Storage (Free Tier)

**Benefits:**
- ChromaDB uses 50-200MB RAM → External service uses 0MB
- Free tier: 1 index, 100K vectors
- Better scalability

**Steps:**
1. Sign up: https://www.pinecone.io (free tier)
2. Create index
3. Install: `pip install pinecone-client`
4. Replace ChromaDB with Pinecone in `src/ingestion.py`

**Cost:** Free for small projects

### 2. Use OpenAI Embeddings (Very Cheap)

**Benefits:**
- Embedding model uses ~80MB RAM → API calls use 0MB
- Very cheap: ~$0.0001 per 1K tokens
- Better quality embeddings

**Steps:**
1. Get OpenAI API key (free tier available)
2. Install: `pip install openai`
3. Replace sentence-transformers with OpenAI API calls

**Cost:** ~$0.10-1.00/month for typical usage

### 3. Keep Ollama External (Already Done ✅)

You already have Ollama separate - good!

---

## 📊 Memory Comparison

### Current Setup (Railway):
- FastAPI: ~50-100MB
- Embedding model: ~80MB
- ChromaDB: ~50-200MB
- Cache: ~10-50MB
- **Total: ~200-400MB** ❌ (Too much for Railway free tier)

### With External Services:
- FastAPI: ~50-100MB
- Pinecone: 0MB (external)
- OpenAI embeddings: 0MB (API calls)
- Cache: 0MB (disabled)
- **Total: ~50-100MB** ✅ (Fits anywhere!)

---

## 🎯 My Recommendation

### Try in This Order:

1. **First: Switch to Render** (easiest, likely to work)
   - Better free tier
   - Similar to Railway
   - No code changes

2. **If Render still fails: Disable caching + reduce context**
   - Quick code changes
   - May be enough to fit in free tier

3. **If still fails: Use Pinecone** (external vector DB)
   - Requires code changes
   - Eliminates ChromaDB memory usage
   - Free tier available

4. **Last resort: Use OpenAI for embeddings**
   - Small cost (~$1/month)
   - Eliminates embedding model memory
   - Better quality

---

## Quick Start: Render Migration

Want me to help you migrate to Render? It's the easiest option and likely to solve your memory issues. The process is:

1. Create Render account (free)
2. Deploy from GitHub (same repo)
3. Set environment variables
4. Done!

No code changes needed - your app should work as-is on Render.

Would you like me to:
- A) Help migrate to Render (recommended)
- B) Implement ultra-aggressive optimizations (disable caching, etc.)
- C) Help integrate Pinecone (external vector DB)
- D) Something else?
