# Streamlit Cloud Deployment Guide

This guide explains how to deploy the Incident Assistant on Streamlit Cloud.

## ⚠️ Important: Architecture Overview

The Incident Assistant consists of **two separate services**:

1. **FastAPI Backend** (`src/api.py`) - Handles authentication, document processing, queries, analytics
2. **Streamlit Frontend** (`src/app.py`) - The user interface

**Streamlit Cloud can only host the frontend.** The FastAPI backend must be deployed separately.

---

## 📋 Prerequisites

1. **Deploy the FastAPI backend** to one of these platforms:
   - [Railway](https://railway.app) (Recommended - Easy setup)
   - [Render](https://render.com) (Free tier available)
   - [Fly.io](https://fly.io) (Good performance)
   - [Heroku](https://heroku.com) (Paid plans)
   - [DigitalOcean App Platform](https://www.digitalocean.com/products/app-platform)
   - Your own VPS/server

2. **Get your backend API URL** (e.g., `https://your-api.railway.app` or `https://your-api.onrender.com`)

---

## 🚀 Step 1: Deploy FastAPI Backend

### Option A: Railway (Recommended - Easiest)

1. Go to [railway.app](https://railway.app) and sign up
2. Click "New Project" → "Deploy from GitHub repo"
3. Select your `incident-assistant` repository
4. Railway will auto-detect the `Dockerfile` and use it
5. Set these environment variables in Railway dashboard:
   ```
   SECRET_KEY=your-secret-key-here
   OLLAMA_HOST=http://localhost:11434  # Or your Ollama instance URL
   EMBEDDING_MODEL=all-mpnet-base-v2
   ```
6. Railway will automatically:
   - Build the Docker image (using optimized multi-stage Dockerfile)
   - Run the API server
7. Railway will give you a URL like `https://your-app.railway.app`

**⚠️ Important:** If you see "Image size exceeded limit" error:
- The optimized Dockerfile should fix this (reduces from ~8.7GB to ~1.5-2.5GB)
- See `RAILWAY_DEPLOYMENT_FIX.md` for details
- If still too large, consider using a lighter embedding model or upgrading Railway plan

### Option B: Render

1. Go to [render.com](https://render.com) and sign up
2. Click "New" → "Web Service"
3. Connect your GitHub repository
4. Configure:
   - **Name:** `incident-assistant-api`
   - **Environment:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn src.api:app --host 0.0.0.0 --port $PORT`
5. Add environment variables:
   ```
   SECRET_KEY=your-secret-key-here
   OLLAMA_HOST=http://localhost:11434
   EMBEDDING_MODEL=all-mpnet-base-v2
   ```
6. Render will give you a URL like `https://incident-assistant-api.onrender.com`

### Option C: Fly.io

1. Install Fly CLI: `curl -L https://fly.io/install.sh | sh`
2. Login: `fly auth login`
3. Create app: `fly launch`
4. Set secrets:
   ```bash
   fly secrets set SECRET_KEY=your-secret-key-here
   fly secrets set OLLAMA_HOST=http://localhost:11434
   ```
5. Deploy: `fly deploy`
6. Get URL: `fly info`

---

## 🎨 Step 2: Deploy Streamlit Frontend to Streamlit Cloud

1. **Push your code to GitHub** (if not already done)
   ```bash
   git add .
   git commit -m "Prepare for Streamlit Cloud deployment"
   git push
   ```

2. **Go to [share.streamlit.io](https://share.streamlit.io)**
   - Sign in with GitHub
   - Click "New app"

3. **Configure your app:**
   - **Repository:** Select `incident-assistant`
   - **Branch:** `main` (or your branch)
   - **Main file path:** `src/app.py`

4. **Set Environment Variables** (Click "Advanced settings" → "Secrets"):
   ```toml
   API_URL = "https://your-api.railway.app"  # Your backend URL from Step 1
   ```
   
   **Important:** Replace `https://your-api.railway.app` with your actual backend URL!

5. **Click "Deploy"**

6. Streamlit Cloud will:
   - Install dependencies from `requirements.txt`
   - Run `streamlit run src/app.py`
   - Give you a URL like `https://your-app.streamlit.app`

---

## ✅ Step 3: Verify Deployment

1. **Test the backend:**
   ```bash
   curl https://your-api.railway.app/health
   ```
   Should return: `{"status": "healthy", ...}`

2. **Test the frontend:**
   - Open your Streamlit Cloud URL
   - Try to register/login
   - If you see "Cannot connect to API", check:
     - Is the backend URL correct in Streamlit secrets?
     - Is the backend actually running?
     - Are there CORS issues? (See troubleshooting below)

---

## 🔧 Troubleshooting

### Error: "Cannot connect to API"

**Possible causes:**

1. **Wrong API_URL:**
   - Check Streamlit Cloud secrets → Ensure `API_URL` is set correctly
   - The URL should be `https://...` (not `http://`)
   - No trailing slash: `https://api.example.com` (not `https://api.example.com/`)

2. **Backend not running:**
   - Check your backend deployment logs
   - Verify the backend is accessible: `curl https://your-api-url/health`

3. **CORS issues:**
   - The backend needs to allow requests from Streamlit Cloud
   - Check `src/api.py` for CORS configuration
   - Add your Streamlit URL to allowed origins

4. **Network/firewall:**
   - Some platforms block outbound connections
   - Check if your backend platform allows connections from Streamlit Cloud

### Error: "Connection timeout"

- Backend might be sleeping (free tier platforms often sleep after inactivity)
- First request after sleep can take 30-60 seconds
- Consider upgrading to a paid plan or using a platform that doesn't sleep

### Error: "401 Unauthorized" or "403 Forbidden"

- Check if authentication is working
- Verify JWT tokens are being sent correctly
- Check backend logs for authentication errors

---

## 🔒 Security Considerations

1. **HTTPS Only:**
   - Always use `https://` URLs (not `http://`)
   - Streamlit Cloud and most platforms provide HTTPS automatically

2. **Environment Variables:**
   - Never commit secrets to GitHub
   - Use platform secrets/environment variables
   - Rotate `SECRET_KEY` regularly

3. **CORS Configuration:**
   - Only allow your Streamlit Cloud domain
   - Don't use `*` in production

4. **API Keys:**
   - If using external services, store keys in environment variables
   - Never hardcode in source code

---

## 📝 Quick Reference

### Backend Deployment Checklist

- [ ] Backend deployed and accessible
- [ ] Backend URL obtained (e.g., `https://api.example.com`)
- [ ] Backend health check works: `curl https://api.example.com/health`
- [ ] CORS configured to allow Streamlit Cloud domain
- [ ] Environment variables set (SECRET_KEY, OLLAMA_HOST, etc.)

### Streamlit Cloud Checklist

- [ ] Code pushed to GitHub
- [ ] Streamlit Cloud app created
- [ ] `API_URL` secret set correctly
- [ ] App deployed successfully
- [ ] Can access login/register page
- [ ] Can connect to backend API

---

## 🆘 Need Help?

1. **Check backend logs** in your deployment platform
2. **Check Streamlit Cloud logs** (click "Manage app" → "Logs")
3. **Test API directly:**
   ```bash
   curl -X POST https://your-api-url/auth/register \
     -H "Content-Type: application/json" \
     -d '{"username":"test","email":"test@example.com","password":"test123"}'
   ```
4. **Open an issue** on GitHub with:
   - Your backend platform
   - Your backend URL (you can redact sensitive parts)
   - Error messages from logs
   - Steps to reproduce

---

## 💡 Alternative: Single-Platform Deployment

If you want both services on one platform, consider:

- **Docker on Railway/Render:** Deploy both services in one container
- **Fly.io:** Run multiple processes in one app
- **Your own VPS:** Full control, run both services

See `DEPLOYMENT_GUIDE.md` for more options.

