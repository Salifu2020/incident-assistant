# Railway Deployment Fix - Image Size Issue

## Problem
Your Railway deployment failed because the Docker image size (8.7 GB) exceeded Railway's 4.0 GB limit.

## Root Causes
1. **sentence-transformers** downloads large ML models (500MB-2GB+) at build time
2. **ChromaDB** and dependencies are large
3. **No .dockerignore** - unnecessary files included
4. **Single-stage build** - build tools included in final image
5. **Models downloaded at build time** instead of runtime

## Solution: Optimized Dockerfile

I've created an optimized Dockerfile that:
- ✅ Uses **multi-stage builds** (build tools not in final image)
- ✅ Excludes unnecessary files with **.dockerignore**
- ✅ Downloads models at **runtime** (not build time)
- ✅ Uses smaller base image
- ✅ Removes build dependencies from final image

### Expected Size Reduction
- **Before:** ~8.7 GB
- **After:** ~1.5-2.5 GB (models downloaded at runtime)

---

## Quick Fix Steps

### 1. Clear Railway Build Cache (CRITICAL)

**Railway might be using a cached build!** You MUST clear the cache:

1. Go to Railway dashboard
2. Click on your service (`incident-assistant`)
3. Click **"Settings"** tab
4. Scroll down to **"Build"** section
5. Click **"Clear Build Cache"**
6. Go back to **"Deployments"** tab
7. Click **"Redeploy"** or push a new commit

### 2. Verify Dockerfile is Being Used

The optimized `Dockerfile` should:
- Use multi-stage builds
- Prevent model downloads during build
- Use lighter default model (`all-MiniLM-L6-v2`)

If Railway still fails, try the ultra-minimal version:
```bash
# Rename the minimal version
mv Dockerfile Dockerfile.standard
mv Dockerfile.minimal Dockerfile
git add Dockerfile
git commit -m "Use minimal Dockerfile for Railway"
git push
```

### 3. Check Build Logs

In Railway, click **"View logs"** on the failed deployment and look for:
- Image size at each stage
- Whether models are being downloaded
- Any cache-related messages

### 2. Verify .dockerignore is Working

The `.dockerignore` file excludes:
- Log files
- Database files (.chromadb/)
- Data directories
- Documentation files
- Large files (PDFs, etc.)

### 3. Deploy Again

Railway should now build a much smaller image.

---

## Alternative: Further Size Reduction

If the image is still too large, consider:

### Option 1: Use External Ollama Service

Instead of running Ollama in the container:
- Use [Ollama Cloud](https://ollama.com/cloud) (if available)
- Deploy Ollama separately
- Point `OLLAMA_HOST` to external service

### Option 2: Use Lighter Embedding Model

In your environment variables, use a smaller model:
```env
EMBEDDING_MODEL=all-MiniLM-L6-v2  # ~80MB instead of ~420MB
```

### Option 3: Download Models to Persistent Volume

Instead of downloading models in the image:
1. Mount a persistent volume for model cache
2. Models download on first run and persist

### Option 4: Upgrade Railway Plan

If you need the full image:
- Railway Pro plan has higher limits
- Or use a different platform (Render, Fly.io)

---

## Verification

After deployment, check image size:

```bash
# In Railway dashboard
# Go to: Service → Metrics → Image Size
```

Or check locally:
```bash
docker build -t incident-assistant .
docker images | grep incident-assistant
```

---

## Troubleshooting

### Still Too Large?

1. **Check what's taking space:**
   ```bash
   docker build -t test .
   docker run --rm test du -sh /app/* | sort -h
   ```

2. **Remove unused dependencies:**
   - Review `requirements.txt`
   - Remove packages you don't use
   - Use lighter alternatives

3. **Use Alpine base image:**
   ```dockerfile
   FROM python:3.11-alpine
   ```
   (Smaller but may have compatibility issues)

### Models Not Downloading at Runtime?

If models fail to download:
1. Check internet connectivity in container
2. Verify `TRANSFORMERS_CACHE` and `SENTENCE_TRANSFORMERS_HOME` are set
3. Check logs for download errors

### Build Fails?

1. **Clear Railway build cache**
2. **Check build logs** for specific errors
3. **Verify .dockerignore** isn't excluding needed files

---

## Expected Build Time

- **First build:** 5-10 minutes (downloads dependencies)
- **Subsequent builds:** 2-5 minutes (cached layers)

---

## Next Steps

1. ✅ Push the updated `Dockerfile` and `.dockerignore` to GitHub
2. ✅ Railway will auto-detect and rebuild
3. ✅ Monitor build logs for size
4. ✅ Verify deployment succeeds

---

## Additional Resources

- [Docker Multi-stage Builds](https://docs.docker.com/build/building/multi-stage/)
- [Railway Limits](https://docs.railway.app/reference/limits)
- [Optimizing Docker Images](https://docs.docker.com/build/guide/optimizing-builds/)

