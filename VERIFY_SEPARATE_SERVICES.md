# How to Verify Ollama Service is Separate on Railway

This guide helps you verify that your Ollama service is running separately from your API service on Railway, ensuring they don't share memory or resources.

## Quick Verification Steps

### 1. Check Railway Dashboard

1. **Go to Railway Dashboard**: https://railway.app/dashboard
2. **Select your project** (incident-assistant or similar)
3. **Look for service list** - You should see **TWO separate services**:
   - `incident-assistant` (or similar - your API service)
   - `ollama` (or similar - your Ollama service)

**✅ If you see TWO services listed separately, they are separate!**

### 2. Check Service Details

For each service, verify:

#### API Service:
1. Click on your **API service** (incident-assistant)
2. Check **Settings** → **General**:
   - **Service Name**: Should be something like `incident-assistant` or your repo name
   - **Source**: Should point to your GitHub repo
   - **No Ollama dependencies** listed

#### Ollama Service:
1. Click on your **Ollama service**
2. Check **Settings** → **General**:
   - **Service Name**: Should be `ollama` or similar
   - **Source**: Should be either:
     - Railway template (`ollama/ollama` template)
     - Docker image (`ollama/ollama:latest`)
     - Or separate GitHub repo/service
   - **NOT the same source as your API service**

### 3. Check Memory Allocation

Each service should have **separate memory limits**:

1. For **API service**: Go to **Settings** → **Resources**
   - Check memory allocation (should be separate from Ollama)
   - Typical: 1-2GB for API service

2. For **Ollama service**: Go to **Settings** → **Resources**
   - Check memory allocation (should be separate from API)
   - Typical: 4-8GB for Ollama service

**✅ If each service has its own memory allocation, they are separate!**

### 4. Check Deployment Logs

#### API Service Logs:
1. Go to your **API service**
2. Click **Deployments** tab
3. Check recent deployment logs
4. Should **NOT** show Ollama startup messages
5. Should show FastAPI/Python startup messages

#### Ollama Service Logs:
1. Go to your **Ollama service**
2. Click **Deployments** tab
3. Check recent deployment logs
4. Should show Ollama-specific startup messages
5. Should **NOT** show FastAPI/Python messages

**✅ If logs are different for each service, they are separate!**

### 5. Check Network Configuration

Both services should have **separate networking**:

1. **API Service**: 
   - **Settings** → **Networking**
   - Should have its own public/private domain
   - Should NOT reference Ollama internally (unless configured via OLLAMA_HOST)

2. **Ollama Service**:
   - **Settings** → **Networking**
   - Should have its own internal domain (e.g., `ollama.railway.internal`)
   - Should expose port `11434`

### 6. Verify OLLAMA_HOST Configuration

In your **API service**:

1. Go to **Settings** → **Variables**
2. Check for `OLLAMA_HOST` variable
3. Value should be:
   - `http://ollama:11434` (internal networking)
   - OR `https://ollama-production-xxxxx.up.railway.app` (public URL)

**✅ If OLLAMA_HOST points to a different service, they are separate!**

## What to Look For (Red Flags)

### ❌ Signs Services Are NOT Separate:

1. **Only ONE service listed** in Railway dashboard
2. **Same source/repo** for both "services" (might be same service with multiple processes)
3. **Shared memory allocation** (both services show same memory usage)
4. **API logs show Ollama startup** messages
5. **No OLLAMA_HOST variable** (might mean Ollama is running in same container)

### ✅ Signs Services ARE Separate:

1. **TWO distinct services** in Railway dashboard
2. **Different sources** (API from GitHub, Ollama from template/Docker)
3. **Separate memory allocations** visible
4. **Different log outputs** for each service
5. **OLLAMA_HOST configured** in API service pointing to Ollama service

## How to Check Memory Usage

1. **API Service**: Go to **Metrics** tab
   - Should show memory usage around 50-200MB at startup
   - Should NOT spike to GB levels (unless loading models)

2. **Ollama Service**: Go to **Metrics** tab
   - Should show memory usage around 100-500MB at startup
   - Will spike to 2-4GB when model is loaded

**✅ If memory usage is tracked separately for each service, they are separate!**

## Common Setup Scenarios

### Scenario 1: Separate Services (✅ CORRECT)
```
Railway Project: incident-assistant
├── Service 1: incident-assistant (API)
│   ├── Source: GitHub repo
│   ├── Memory: 1GB
│   └── OLLAMA_HOST: http://ollama:11434
│
└── Service 2: ollama
    ├── Source: Railway template / Docker
    ├── Memory: 4GB
    └── Port: 11434
```
**This is the correct setup!**

### Scenario 2: Same Service (❌ WRONG)
```
Railway Project: incident-assistant
└── Service 1: incident-assistant
    ├── Runs both API and Ollama
    ├── Memory: Shared (causes crashes)
    └── Dockerfile runs both processes
```
**This is problematic - they share memory!**

## If Services Are NOT Separate

If you discover they're running in the same service:

1. **Create separate Ollama service**:
   - In Railway, click **"New"** → **"Empty Service"**
   - Use Ollama Docker image: `ollama/ollama:latest`
   - Or use Railway Ollama template

2. **Configure API service**:
   - Set `OLLAMA_HOST` environment variable
   - Point to the new Ollama service URL

3. **Redeploy both services**

## Testing Separation

After verification, test that they're truly separate:

1. **Stop Ollama service** (temporarily)
2. **API service should still start** (won't crash)
3. **API service should start successfully** (just can't make queries)
4. **Start Ollama service again**
5. **Queries should work**

**✅ If API starts without Ollama, they are truly separate!**

## Summary Checklist

- [ ] Two separate services visible in Railway dashboard
- [ ] Different sources/configuration for each service
- [ ] Separate memory allocations visible
- [ ] Different log outputs
- [ ] OLLAMA_HOST configured in API service
- [ ] API service can start without Ollama running
- [ ] Memory metrics tracked separately

If all checkboxes are ✅, your services are properly separated!

