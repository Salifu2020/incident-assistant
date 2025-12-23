# Step-by-Step Migration Guide: Railway → Render

This guide will help you migrate your Incident Assistant API from Railway to Render.

## Prerequisites

- [x] GitHub repository connected (already done)
- [ ] Render account (we'll create this)
- [ ] Your Ollama service URL (from Railway fearless-prosperity project)

---

## Step 1: Create Render Account

1. Go to **https://render.com**
2. Click **"Get Started for Free"** or **"Sign Up"**
3. Sign up with your GitHub account (recommended - easiest)
4. Authorize Render to access your GitHub repositories

---

## Step 2: Create New Web Service

1. Once logged in, click **"New +"** in the top right
2. Select **"Web Service"**
3. You'll see a list of your GitHub repositories
4. Find and click **"incident-assistant"** repository
5. Click **"Connect"**

---

## Step 3: Configure the Service

Render will auto-detect Python, but verify these settings:

### Basic Settings:
- **Name**: `incident-assistant-api` (or any name you prefer)
- **Region**: Choose closest to you (e.g., `Oregon (US West)` or `Frankfurt (EU Central)`)
- **Branch**: `main` (should be auto-detected)
- **Root Directory**: Leave blank (or `.` if needed)
- **Runtime**: `Python 3`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python run_api.py`
- **Plan**: Select **"Free"** (512MB RAM, enough for your optimized app)

### Advanced Settings (click "Advanced"):
- **Dockerfile Path**: Leave blank (Render will use Nixpacks/auto-detect)
- **Docker Context**: Leave blank

---

## Step 4: Set Environment Variables

In the same configuration screen, scroll down to **"Environment Variables"** section:

Click **"Add Environment Variable"** for each:

1. **SECRET_KEY**
   - Key: `SECRET_KEY`
   - Value: `your-secret-key-here` (use the same one from Railway, or generate a new one)
   - Click **"Add"**

2. **OLLAMA_HOST**
   - Key: `OLLAMA_HOST`
   - Value: Your Ollama public URL from Railway (`fearless-prosperity` project)
     - Should be: `https://ollama-production-xxxxx.up.railway.app` (the URL you generated earlier)
   - Click **"Add"**

3. **EMBEDDING_MODEL**
   - Key: `EMBEDDING_MODEL`
   - Value: `all-MiniLM-L6-v2`
   - Click **"Add"**

4. **LLM_MODEL**
   - Key: `LLM_MODEL`
   - Value: `phi3:mini`
   - Click **"Add"**

5. **PYTHONUNBUFFERED**
   - Key: `PYTHONUNBUFFERED`
   - Value: `1`
   - Click **"Add"**

6. **PYTHONPATH**
   - Key: `PYTHONPATH`
   - Value: `/opt/render/project/src`
   - Click **"Add"**

**Note**: Render automatically sets `PORT` environment variable, so you don't need to set it manually.

---

## Step 5: Deploy

1. Scroll to bottom of configuration page
2. Click **"Create Web Service"**
3. Render will start building and deploying your service
4. Wait for deployment to complete (usually 2-5 minutes)

**You'll see build logs** showing:
- Installing dependencies
- Building the application
- Starting the service

---

## Step 6: Get Your Render URL

Once deployment completes:

1. You'll see **"Your service is live"** message
2. Your service URL will be shown (e.g., `https://incident-assistant-api.onrender.com`)
3. **Copy this URL** - you'll need it for Streamlit

---

## Step 7: Update Streamlit Cloud Configuration

1. Go to **Streamlit Cloud** dashboard
2. Select your app
3. Go to **Settings** → **Secrets** (or click the "⋮" menu → "Settings")
4. Find the `API_URL` secret
5. Update it to your new Render URL:
   ```
   API_URL = "https://incident-assistant-api.onrender.com"
   ```
6. Save and redeploy Streamlit app

---

## Step 8: Test the Migration

1. **Test API Health**:
   - Visit: `https://your-render-url.onrender.com/health`
   - Should return: `{"status": "healthy"}`

2. **Test from Streamlit**:
   - Go to your Streamlit app
   - Try logging in
   - Try uploading a document
   - Try asking a question

---

## Troubleshooting

### Build Fails

**Check build logs** in Render dashboard:
- Look for error messages
- Common issues:
  - Missing dependencies (check `requirements.txt`)
  - Python version mismatch (Render uses Python 3.11 by default)
  - Build timeout (free tier has limits)

### Service Crashes on Start

**Check service logs**:
- Go to Render dashboard → Your service → **"Logs"** tab
- Look for error messages
- Common issues:
  - Missing environment variables
  - Port binding issues (Render sets PORT automatically, should be fine)
  - Import errors

### Can't Connect to Ollama

**Verify**:
1. `OLLAMA_HOST` is set correctly in Render environment variables
2. Ollama service is still running on Railway
3. Ollama URL is accessible (try `curl https://your-ollama-url/api/tags`)

### Memory Issues on Render

Even with Render's better memory management, if you still hit limits:
- Check logs for OOM (Out of Memory) errors
- Implement ultra-aggressive optimizations (see `DEPLOYMENT_ALTERNATIVES.md`)
- Consider external services (Pinecone, OpenAI)

---

## Render vs Railway - Key Differences

| Feature | Railway | Render |
|---------|---------|--------|
| Free Tier RAM | ~512MB-1GB (strict) | 512MB (more flexible) |
| Memory Management | Stricter limits | More forgiving |
| Build Process | Nixpacks/Docker | Nixpacks (auto-detect) |
| Environment | Similar | Similar |
| Auto-deploy | Yes | Yes |
| Free Tier Hours | 500 hours/month | 750 hours/month |

**Render is generally better** for Python applications with memory constraints.

---

## Keeping Both (Optional)

You can keep both Railway and Render running:
- Use Railway for Ollama (keep it there)
- Use Render for API (migrate here)
- Update Streamlit to point to Render

Or migrate Ollama to Render too (in same project for internal networking).

---

## Migration Checklist

- [ ] Created Render account
- [ ] Created new Web Service
- [ ] Configured build and start commands
- [ ] Set all environment variables (SECRET_KEY, OLLAMA_HOST, etc.)
- [ ] Deployed successfully
- [ ] Got Render service URL
- [ ] Updated Streamlit API_URL secret
- [ ] Tested API health endpoint
- [ ] Tested document upload from Streamlit
- [ ] Tested queries from Streamlit
- [ ] Verified Ollama connection works

---

## Next Steps After Migration

1. **Monitor Render logs** for the first few hours
2. **Test all functionality** thoroughly
3. **Update any documentation** with new URLs
4. **Consider migrating Ollama** to Render too (optional, for better integration)

Once everything works on Render, you can:
- Keep Railway services running as backup (optional)
- Or delete Railway services to save resources

---

## Need Help?

If you encounter any issues during migration:
1. Check Render logs (most helpful)
2. Compare with Railway logs (if still accessible)
3. Verify environment variables are set correctly
4. Test API endpoints directly (curl or browser)

The migration should be straightforward since your app is already optimized and uses environment variables properly!

