# Modern Stack Setup Guide

This guide explains the upgraded architecture that replaces self-hosted Ollama with cloud LLM APIs and enables pgvector for persistent vector storage.

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Streamlit      │────▶│  FastAPI on     │────▶│  Supabase       │
│  Cloud          │     │  Render / Fly   │     │  (Postgres +    │
│  (Frontend)     │     │  (Stateless)    │     │   pgvector)     │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │  Groq / OpenAI  │
                        │  (LLM API)      │
                        └─────────────────┘
```

## Benefits

- ✅ **No Ollama to manage** - Use Groq/OpenAI API instead
- ✅ **No ChromaDB memory issues** - Use pgvector in Supabase
- ✅ **Single database** - Users + vectors in same Postgres
- ✅ **Stateless API** - Easy scaling, no cold start issues
- ✅ **Generous free tiers** - All services have free options

## Quick Setup

### 1. Get a Groq API Key (Free)

1. Go to [console.groq.com](https://console.groq.com)
2. Sign up for free
3. Create an API key
4. Copy the key

### 2. Set Up Supabase (Free)

1. Go to [supabase.com](https://supabase.com)
2. Create a new project
3. Enable pgvector extension:
   - Go to **Database** → **Extensions**
   - Search for "vector" and enable it
4. Get your connection string:
   - Go to **Project Settings** → **Database**
   - Copy the **Connection string** (URI format)

### 3. Configure Environment Variables

Set these environment variables for your deployment:

```bash
# LLM Provider (choose one)
GROQ_API_KEY=your-groq-api-key          # Recommended
# OPENAI_API_KEY=your-openai-api-key    # Alternative
# OLLAMA_HOST=http://localhost:11434    # Fallback (self-hosted)

# LLM Model (optional, has sensible defaults)
LLM_MODEL=llama-3.1-8b-instant          # For Groq
# LLM_MODEL=gpt-3.5-turbo               # For OpenAI
# LLM_MODEL=phi3:mini                   # For Ollama

# Vector Store
DATABASE_URL=postgresql://user:pass@host:5432/postgres
VECTOR_STORE=pgvector                    # Or "chromadb" for local

# Embedding Model (optional)
EMBEDDING_MODEL=all-MiniLM-L6-v2        # Fast, 384 dimensions
# EMBEDDING_MODEL=all-mpnet-base-v2     # Better quality, 768 dimensions
```

## Environment Variable Reference

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `GROQ_API_KEY` | Yes* | Groq API key for LLM | - |
| `OPENAI_API_KEY` | No | OpenAI API key (alternative) | - |
| `OLLAMA_HOST` | No | Ollama server URL (fallback) | http://localhost:11434 |
| `LLM_PROVIDER` | No | Force specific provider | auto |
| `LLM_MODEL` | No | Model name | llama-3.1-8b-instant |
| `DATABASE_URL` | Yes** | Postgres connection string | - |
| `VECTOR_STORE` | No | Vector store type | auto |
| `EMBEDDING_MODEL` | No | Embedding model name | all-MiniLM-L6-v2 |

*Required if not using OpenAI or Ollama
**Required for pgvector; optional for ChromaDB

## LLM Provider Priority

The system automatically selects an LLM provider in this order:

1. **Groq** - If `GROQ_API_KEY` is set
2. **OpenAI** - If `OPENAI_API_KEY` is set
3. **Ollama** - Fallback if server is running

You can force a specific provider with `LLM_PROVIDER=groq|openai|ollama`.

## Groq Model Options

| Model | Speed | Quality | Best For |
|-------|-------|---------|----------|
| `llama-3.1-8b-instant` | ⚡⚡⚡ | Good | Most queries (default) |
| `llama-3.3-70b-versatile` | ⚡⚡ | Excellent | Complex reasoning |
| `mixtral-8x7b-32768` | ⚡⚡ | Good | Long context |
| `gemma2-9b-it` | ⚡⚡⚡ | Good | Instruction following |

## Vector Store Priority

The system automatically selects a vector store:

1. **pgvector** - If `DATABASE_URL` is set and `VECTOR_STORE` != "chromadb"
2. **ChromaDB** - Fallback, always available

You can force ChromaDB with `VECTOR_STORE=chromadb`.

## Deployment Examples

### Render

1. Create Web Service from GitHub repo
2. Add environment variables:
   ```
   GROQ_API_KEY=your-key
   DATABASE_URL=your-supabase-url
   ```
3. Deploy

### Railway

1. Create project from GitHub repo
2. Add environment variables in Settings → Variables
3. Deploy

### Local Development

```bash
# Create .env file
cat > .env << EOF
GROQ_API_KEY=your-groq-api-key
DATABASE_URL=postgresql://user:pass@localhost:5432/incident_assistant
EMBEDDING_MODEL=all-MiniLM-L6-v2
EOF

# Install dependencies
pip install -r requirements.txt

# Run
python run_api.py
```

## Supabase pgvector Setup

After enabling the pgvector extension, the application will automatically:

1. Create a `documents` table with vector column
2. Create indexes for fast similarity search
3. Handle all CRUD operations

The table schema:
```sql
CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    embedding vector(384),  -- Dimension depends on model
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX documents_embedding_idx 
ON documents 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

## Migration from Ollama + ChromaDB

If you have existing data:

1. **ChromaDB data**: Will need to be re-indexed into pgvector
2. **User data**: Already in Postgres, no migration needed

To re-index documents after switching to pgvector:
```bash
python reindex_documents.py
```

## Troubleshooting

### "No LLM provider available"

Check that at least one of these is set:
- `GROQ_API_KEY`
- `OPENAI_API_KEY`
- `OLLAMA_HOST` (and Ollama is running)

### "pgvector extension not found"

Enable it in Supabase:
- Database → Extensions → Search "vector" → Enable

### "Connection refused" to database

Check:
- `DATABASE_URL` is correctly formatted
- Supabase project is active
- IP is allowed in connection pooler settings

## Cost Estimates

| Service | Free Tier | Paid |
|---------|-----------|------|
| **Groq** | Very generous (~100K tokens/day) | Contact sales |
| **Supabase** | 500MB database, 2GB transfers | $25/mo |
| **Render** | 750 hours/mo | $7/mo |
| **Total** | **$0/mo** | ~$32/mo |

## Next Steps

1. Set up monitoring (Sentry, LogFlare)
2. Configure backups for Supabase
3. Set up CI/CD for automatic deployments
4. Add custom domain with SSL
