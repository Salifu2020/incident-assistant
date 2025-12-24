# Railway Deployment Using Nixpacks (No Docker)

This guide shows how to deploy to Railway using **Nixpacks** instead of Docker. Nixpacks automatically detects Python projects and builds them without needing a Dockerfile.

## ✅ Advantages of Nixpacks

- **No Dockerfile needed** - Railway automatically detects and builds Python projects
- **Simpler configuration** - Just `Procfile` and `nixpacks.toml`
- **Automatic optimization** - Railway handles the build process
- **No image size issues** - Models download at runtime, not build time
- **Faster builds** - No Docker layer caching complexity

---

## 🚀 Quick Setup

### Step 1: Use Nixpacks Instead of Docker

Railway will automatically use Nixpacks if:
1. There's a `Procfile` in the root directory
2. There's a `requirements.txt` file
3. No `Dockerfile` is present (or it's ignored)

**Option A: Temporarily rename Dockerfile**
```bash
git mv Dockerfile Dockerfile.docker
git add .
git commit -m "Switch to Nixpacks deployment"
git push
```

**Option B: Delete Dockerfile** (if you don't need it)
```bash
git rm Dockerfile
git add .
git commit -m "Remove Dockerfile, use Nixpacks"
git push
```

### Step 2: Verify Files Are Present

Make sure you have:
- ✅ `Procfile` - Tells Railway how to start the app
- ✅ `nixpacks.toml` - Optional configuration (already created)
- ✅ `requirements.txt` - Python dependencies
- ✅ `run_api.py` - Entry point (updated to use Railway's PORT)

### Step 3: Deploy on Railway

1. Go to Railway dashboard
2. Your service should automatically detect the change
3. Railway will use Nixpacks instead of Docker
4. The build should be faster and simpler

---

## 📋 What Each File Does

### `Procfile`
```
web: python run_api.py
```
- Tells Railway this is a web service
- Command to start the application
- Railway will automatically assign a PORT

### `nixpacks.toml`
- Configures the Nixpacks build process
- Sets environment variables
- Defines build phases
- Configures model cache locations

### `run_api.py` (Updated)
- Now reads `PORT` from environment (Railway provides this)
- Uses `0.0.0.0` as host (required for Railway)
- Falls back to defaults if not on Railway

---

## 🔧 Environment Variables

Set these in Railway dashboard (Settings → Variables):

```
SECRET_KEY=your-secret-key-here
OLLAMA_HOST=http://localhost:11434
EMBEDDING_MODEL=all-MiniLM-L6-v2
PORT=8000  # Railway sets this automatically, but you can override
```

---

## 🆚 Nixpacks vs Docker

| Feature | Docker | Nixpacks |
|---------|--------|----------|
| Configuration | Dockerfile | Procfile + nixpacks.toml |
| Build Time | 5-10 min | 3-5 min |
| Image Size | Can be large | Optimized automatically |
| Complexity | High | Low |
| Debugging | Docker logs | Railway build logs |
| Model Downloads | Must prevent at build | Automatic at runtime |

---

## 🐛 Troubleshooting

### Railway Still Uses Docker

If Railway still tries to use Docker:
1. Make sure `Dockerfile` is renamed or deleted
2. Clear Railway build cache (Settings → Build → Clear Cache)
3. Redeploy

### Build Fails

Check Railway build logs for:
- Missing dependencies in `requirements.txt`
- Python version issues (Nixpacks uses Python 3.11 by default)
- Port binding errors

### Models Not Downloading

Models download on first API call. If they don't:
1. Check `TRANSFORMERS_CACHE` and `SENTENCE_TRANSFORMERS_HOME` are set
2. Verify internet connectivity in Railway
3. Check API logs for download errors

---

## 📊 Expected Results

- **Build Time:** 3-5 minutes (vs 5-10 for Docker)
- **Deployment Size:** No image size limits (models download at runtime)
- **Startup Time:** ~30 seconds (first request may be slower due to model download)

---

## 🔄 Switching Back to Docker

If you want to use Docker again:
```bash
git mv Dockerfile.docker Dockerfile
git rm Procfile nixpacks.toml
git commit -m "Switch back to Docker"
git push
```

---

## ✅ Next Steps

1. Rename or remove `Dockerfile`
2. Commit and push changes
3. Railway will automatically detect and use Nixpacks
4. Monitor the build logs
5. Verify deployment succeeds

The Nixpacks approach should be much simpler and avoid all the Docker image size issues!


