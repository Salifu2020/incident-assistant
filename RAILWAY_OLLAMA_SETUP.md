# Railway Ollama Service Setup Guide

This guide explains how to deploy Ollama as a separate Railway service and connect it to your Incident Assistant API.

## Why Separate Ollama Service?

- **Memory Management**: Keeps LLM memory usage separate from your API
- **Independent Scaling**: Scale Ollama separately based on query load
- **Better Stability**: Prevents memory crashes in your main API service
- **Resource Isolation**: Each service can have its own resource limits

## Step 1: Deploy Ollama Service on Railway

### Option A: One-Click Template (Recommended)

1. Go to [Railway Ollama Template](https://railway.app/template/ollama)
2. Click **"Deploy on Railway"**
3. Railway will create a new service with Ollama pre-configured
4. Wait for deployment to complete
5. Note the service URL (e.g., `https://ollama-production-xxxxx.up.railway.app`)

### Option B: Manual Docker Deployment

1. In your Railway project, click **"New"** → **"Empty Service"**
2. Click **"Settings"** → **"Deploy"**
3. Select **"Docker"** as the deployment method
4. Add this Dockerfile:

```dockerfile
FROM ollama/ollama:latest

# Expose Ollama port
EXPOSE 11434

# Ollama runs automatically on container start
CMD ["ollama", "serve"]
```

5. In **"Settings"** → **"Networking"**, expose port `11434`
6. Deploy the service

## Step 2: Pull Required Model

Once Ollama service is running:

1. Go to your Ollama service in Railway dashboard
2. Click **"Deploy Logs"** or **"View Logs"**
3. Open a terminal/console (Railway provides this)
4. Run:
   ```bash
   ollama pull phi3:mini
   ```
   (Or whatever model you configured in `LLM_MODEL` environment variable)

**Alternative**: Use Railway's web terminal or connect via SSH if available.

## Step 3: Configure API Service to Use Ollama

### Get Ollama Service URL

Railway provides two ways to connect:

1. **Public URL** (e.g., `https://ollama-production-xxxxx.up.railway.app`)
2. **Private/Internal URL** (e.g., `http://ollama:11434` if services are in same project)

### Set OLLAMA_HOST Environment Variable

1. Go to your **API service** (incident-assistant) in Railway
2. Click **"Settings"** → **"Variables"**
3. Add new variable:
   - **Name**: `OLLAMA_HOST`
   - **Value**: 
     - For public URL: `https://ollama-production-xxxxx.up.railway.app` (use HTTPS)
     - For internal URL: `http://ollama:11434` (if both services in same project)
4. Click **"Add"**

### Verify Configuration

The Ollama Python library automatically uses the `OLLAMA_HOST` environment variable. No code changes needed!

## Step 4: Test the Connection

1. Make a query through your API
2. Check Railway logs for your API service
3. You should see successful Ollama connections (no "Failed to connect" errors)

## Troubleshooting

### "Failed to connect to Ollama"

**Check:**
1. Is Ollama service running? Check Railway dashboard
2. Is `OLLAMA_HOST` set correctly in API service?
3. Is the model pulled? Run `ollama list` in Ollama service terminal
4. Are both services in the same Railway project? (for internal networking)

### Model Not Found

**Solution:**
1. Connect to Ollama service terminal
2. Run: `ollama pull phi3:mini` (or your configured model)
3. Verify: `ollama list` should show the model

### Port Issues

**If using public URL:**
- Make sure Ollama service exposes port 11434
- Railway automatically handles HTTPS for public URLs
- Use `https://` in `OLLAMA_HOST`, not `http://`

**If using internal URL:**
- Both services must be in the same Railway project
- Use `http://ollama:11434` format
- Service name must match exactly

## Railway Internal Networking

If both services are in the same Railway project:

1. Railway automatically creates internal networking
2. Use service name as hostname: `http://ollama:11434`
3. This is faster and more secure (no public exposure)

**To find service name:**
- Go to Ollama service → Settings → General
- Service name is shown at the top

## Environment Variables Summary

### API Service Variables:
```env
OLLAMA_HOST=http://ollama:11434  # or https://ollama-production-xxxxx.up.railway.app
LLM_MODEL=phi3:mini
EMBEDDING_MODEL=all-MiniLM-L6-v2
SECRET_KEY=your-secret-key
```

### Ollama Service Variables:
```env
# Usually no variables needed - Ollama runs with defaults
# But you can set:
OLLAMA_HOST=0.0.0.0:11434  # Listen on all interfaces
```

## Resource Recommendations

### Ollama Service:
- **Memory**: 4GB minimum (for phi3:mini), 8GB recommended
- **CPU**: 2+ cores recommended
- **Storage**: 10GB+ (for models)

### API Service:
- **Memory**: 1-2GB (now that LLM is separate!)
- **CPU**: 1-2 cores
- **Storage**: 5GB+

## Monitoring

Monitor both services in Railway dashboard:
- **Ollama Service**: Check memory usage, model loading times
- **API Service**: Check memory usage (should be much lower now!)

## Next Steps

1. Deploy Ollama service
2. Pull the model (`ollama pull phi3:mini`)
3. Set `OLLAMA_HOST` in API service
4. Redeploy API service (or it will auto-redeploy)
5. Test with a query

Your document uploads should work immediately, and queries will work once Ollama is connected!

