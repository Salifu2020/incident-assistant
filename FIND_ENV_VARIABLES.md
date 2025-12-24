# How to Find Your Environment Variables

This guide will help you find or generate the values you need for Render deployment.

---

## 1. Finding SECRET_KEY

**IMPORTANT**: The code actually looks for `JWT_SECRET_KEY`, not `SECRET_KEY`!

### Option A: Check Railway Environment Variables

1. Go to **Railway Dashboard**: https://railway.app
2. Select your **API service** (likely in `luminous-reflection` project)
3. Click on the service name
4. Go to **"Variables"** tab (or **"Settings"** → **"Variables"**)
5. Look for `JWT_SECRET_KEY` or `SECRET_KEY` in the list
6. Click the eye icon (👁️) to reveal the value
7. **Copy the value**

**Note**: If you see `SECRET_KEY` but not `JWT_SECRET_KEY`, that's okay - you can use the same value.

### Option B: Check Railway Service Settings

1. Go to your API service in Railway
2. Click **"Settings"** tab
3. Scroll to **"Environment Variables"** section
4. Find `SECRET_KEY` and copy its value

### Option C: Generate a New SECRET_KEY (if not found)

If you can't find the SECRET_KEY in Railway, you can generate a new one:

**Quick method - Run this script:**
```bash
python generate_secret_key.py
```

**Or using Python directly:**
```python
import secrets
print(secrets.token_urlsafe(32))
```

**Using OpenSSL (command line):**
```bash
openssl rand -hex 32
```

**Using PowerShell (Windows):**
```powershell
-join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
```

**Or use this online generator:**
- https://randomkeygen.com/ (use "CodeIgniter Encryption Keys")

**Note**: If you generate a new SECRET_KEY, existing users may need to log in again (their sessions will be invalid).

---

## 2. Finding OLLAMA_HOST

### Check Railway Ollama Service

The `OLLAMA_HOST` should point to your Ollama service running in Railway.

#### Step 1: Find Your Ollama Service

1. Go to **Railway Dashboard**: https://railway.app
2. Look for a project called **"fearless-prosperity"** (you mentioned this earlier)
3. Click on that project
4. You should see an **"ollama"** service

#### Step 2: Get the Ollama Public URL

**Option A: Generate Public URL (Recommended)**

1. In the Ollama service, go to **"Settings"** tab
2. Scroll to **"Networking"** section
3. Find **"Generate Domain"** or **"Public Networking"** section
4. Click **"Generate Domain"** or enable public networking
5. Railway will generate a URL like: `https://ollama-production-xxxxx.up.railway.app`
6. **Copy this URL** - this is your `OLLAMA_HOST`

**Option B: Use Internal Network Name (if services in same project)**

If your Ollama and API services are in the **same Railway project**, you can use:
- `http://ollama:11434` (internal network name)

But since you mentioned they're in different projects (`fearless-prosperity` for Ollama, `luminous-reflection` for API), you **must use the public URL**.

#### Step 3: Test the Ollama URL

Once you have the URL, test it works:

**In browser:**
Visit: `https://your-ollama-url.up.railway.app/api/tags`

Should return JSON like:
```json
{"models":[{"name":"phi3:mini","size":2416125952,...}]}
```

**Or using curl:**
```bash
curl https://your-ollama-url.up.railway.app/api/tags
```

**Or using PowerShell:**
```powershell
Invoke-RestMethod -Uri "https://your-ollama-url.up.railway.app/api/tags"
```

---

## 3. If Ollama Service Doesn't Have a Public URL

### Generate One:

1. In Railway Ollama service:
   - Go to **"Settings"** → **"Networking"**
   - Find **"Public Networking"** or **"Generate Domain"**
   - Enable it or generate domain
   - Copy the generated URL

### Verify Ollama is Running:

1. Check Ollama service logs in Railway
2. Should see messages like:
   ```
   time=2024-... msg="server config" ...
   time=2024-... msg="server config env" ...
   ```

---

## 4. Complete Checklist

Before deploying to Render, make sure you have:

- [ ] **SECRET_KEY**: Found in Railway or generated new one
- [ ] **OLLAMA_HOST**: Public URL from Railway Ollama service (e.g., `https://ollama-production-xxxxx.up.railway.app`)
- [ ] **OLLAMA_HOST tested**: Can access `https://your-ollama-url/api/tags` successfully
- [ ] **Ollama model pulled**: Make sure `phi3:mini` is pulled on Ollama service

---

## 5. Environment Variables Summary for Render

When setting up Render, use these values:

```env
JWT_SECRET_KEY=your-secret-key-from-railway-or-generated
# OR use SECRET_KEY (both work, but JWT_SECRET_KEY is what the code expects)
OLLAMA_HOST=https://ollama-production-xxxxx.up.railway.app
EMBEDDING_MODEL=all-MiniLM-L6-v2
LLM_MODEL=phi3:mini
PYTHONUNBUFFERED=1
```

---

## 6. Quick Commands to Find Values

### Find SECRET_KEY in Railway (if accessible via CLI):

```bash
# If you have Railway CLI installed
railway variables --service your-api-service-name
```

### Test Ollama Connection:

```bash
# Test if Ollama is accessible
curl https://your-ollama-url.up.railway.app/api/tags

# Should return JSON with models list
```

---

## Troubleshooting

### "SECRET_KEY not found"

- Generate a new one (see Option C above)
- If you generate a new one, existing users will need to re-register/log in

### "OLLAMA_HOST has no value"

- This is normal if you haven't generated a public URL for Ollama yet
- Go to Railway Ollama service → Settings → Networking → Generate Domain
- Copy the generated URL

### "Cannot connect to Ollama"

- Verify Ollama service is running in Railway (check logs)
- Verify public URL is generated and accessible
- Test with `curl https://your-ollama-url/api/tags`
- Make sure the model is pulled: SSH into Ollama service and run `ollama pull phi3:mini`

---

## Next Steps

Once you have both values:

1. Set them in Render environment variables
2. Deploy to Render
3. Test the connection
4. Update Streamlit `API_URL` to point to Render

Need help with any specific step? Let me know!

