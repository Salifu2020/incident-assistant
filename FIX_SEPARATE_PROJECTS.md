# Fix: Ollama and API in Separate Railway Projects

You currently have:
- **Project 1**: `fearless-prosperity` (Ollama service)
- **Project 2**: `luminous-reflection` (incident-assistant API)

Since they're in **separate projects**, you need to use **public networking** instead of internal networking.

## Option 1: Use Public URL (Quick Fix)

### Step 1: Get Ollama Public URL

1. Go to **fearless-prosperity** project
2. Click on the **Ollama service**
3. Go to **Settings** → **Networking**
4. Click **"Generate Domain"** or **"Custom Domain"**
5. Note the public URL (e.g., `https://ollama-production-xxxxx.up.railway.app`)

### Step 2: Configure API Service

1. Go to **luminous-reflection** project
2. Click on your **incident-assistant** service
3. Go to **Settings** → **Variables**
4. Add/Update `OLLAMA_HOST`:
   - **Name**: `OLLAMA_HOST`
   - **Value**: `https://ollama-production-xxxxx.up.railway.app` (use the URL from Step 1)
5. Save

### Step 3: Verify Port

Make sure Ollama service exposes port `11434`:
1. In **fearless-prosperity** → Ollama service
2. **Settings** → **Networking**
3. Ensure port `11434` is exposed

## Option 2: Move Ollama to Same Project (Better - Internal Networking)

This allows using `http://ollama:11434` for faster, more secure communication.

### Step 1: Create Ollama Service in Same Project

1. Go to **luminous-reflection** project
2. Click **"New"** → **"Empty Service"**
3. Name it `ollama`
4. **Settings** → **Deploy** → Select **"Docker"**
5. Use Docker image: `ollama/ollama:latest`
6. Or use Railway template: https://railway.app/template/ollama

### Step 2: Configure Networking

1. In the new Ollama service, go to **Settings** → **Networking**
2. Enable **Private Networking** (should be automatic)
3. Note the internal domain: `ollama.railway.internal` or just `ollama`

### Step 3: Update API Service

1. In **luminous-reflection** → **incident-assistant** service
2. **Settings** → **Variables**
3. Update `OLLAMA_HOST` to: `http://ollama:11434`
4. Save

### Step 4: Delete Old Ollama Project (Optional)

Once the new Ollama service is working:
1. You can delete the **fearless-prosperity** project
2. Or keep it as backup

## Which Option to Choose?

### Use Option 1 (Public URL) if:
- ✅ You want a quick fix
- ✅ You don't want to recreate the Ollama service
- ✅ You already have the model pulled in fearless-prosperity

### Use Option 2 (Same Project) if:
- ✅ You want faster communication (internal networking)
- ✅ You want better security (no public exposure)
- ✅ You want easier management (everything in one place)
- ✅ You don't mind recreating the Ollama service

## Recommended: Option 2

Moving Ollama to the same project is better because:
- **Faster**: Internal networking is faster than public URLs
- **More Secure**: No public exposure needed
- **Easier Management**: All services in one place
- **Better Resource Management**: Can see all services together

## Quick Steps for Option 2:

1. In **luminous-reflection** project → **New** → **Empty Service**
2. Name: `ollama`
3. Use Railway Ollama template or Docker image `ollama/ollama:latest`
4. Pull model: `ollama pull phi3:mini`
5. In **incident-assistant** service → Set `OLLAMA_HOST=http://ollama:11434`
6. Done!

## Testing

After configuration:
1. Check API service logs - should connect to Ollama successfully
2. Make a test query - should work without "Failed to connect" errors
3. Check Ollama service logs - should show API requests

