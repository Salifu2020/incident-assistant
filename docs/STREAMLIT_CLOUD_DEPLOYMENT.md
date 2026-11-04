# Streamlit Community Cloud deployment

Incident Assistant is a **two-process** app:

1. **Streamlit UI** (`src/app.py`) — what Community Cloud runs
2. **FastAPI backend** (`python run.py api`) — must be hosted separately (Railway, Render, Fly.io, etc.)

Community Cloud cannot run FastAPI for you. If the UI has no public `API_URL`, login and every feature fail. If `requirements.txt` pulls in `torch` / ChromaDB / sentence-transformers, the Cloud build often sits on a forever spinner or OOMs.

## 1. Deploy the API first

Deploy this repo as an API service (Docker / Railway / Render) using **`requirements-api.txt`**.

### Render (recommended free option)

Root `requirements.txt` is **Streamlit-only**. If Render uses it, you get `ModuleNotFoundError: No module named 'fastapi'`.

In the Render service → **Settings**:

| Field | Value |
|--------|--------|
| Build Command | `pip install -r requirements-api.txt` |
| Start Command | `python run.py api` |

Or use the repo `render.yaml` Blueprint. Set env vars: `GROQ_API_KEY`, `JWT_SECRET_KEY`, and optionally `LLM_PROVIDER` / `LLM_MODEL`.

Free instances are small — first boot can be slow while embeddings/torch load. If the service OOMs, upgrade the plan or use Docker on a larger host.

Confirm:

```bash
curl https://YOUR-API-HOST/health
```

Set the same secrets the API needs (`GROQ_API_KEY`, `JWT_SECRET_KEY`, optional `DATABASE_URL`, etc.).

Allow your Streamlit Cloud origin in CORS if you lock CORS down.

## 2. Deploy the Streamlit app

On [share.streamlit.io](https://share.streamlit.io):

| Setting | Value |
|--------|--------|
| Repository | `Salifu2020/incident-assistant` |
| Branch | `main` (or your deploy branch) |
| Main file path | `src/app.py` |
| Python version | 3.11 or 3.12 |

Root **`requirements.txt`** is frontend-only (includes `requirements-streamlit.txt`). That is intentional so Cloud does not install the RAG stack.

## 3. Required secrets (Manage app → Settings → Secrets)

```toml
API_URL = "https://YOUR-API-HOST"

# Optional — only if you also put backend secrets here for local-style tooling.
# The Streamlit process itself only needs API_URL.
```

After saving secrets, **reboot** the app.

Without `API_URL`, the UI defaults to `http://127.0.0.1:8000`, which does not exist on Cloud. You should see a clear warning on the login screen after this fix ships.

## 4. Forever-loading checklist

| Symptom | Likely cause | Fix |
|--------|----------------|-----|
| Spinner never ends / stuck “in the oven” | Heavy deps or Cloud platform stall | Confirm `requirements.txt` is slim; reboot; redeploy |
| App loads, login fails / connection errors | Missing or wrong `API_URL` | Set secrets; curl `/health` on the API |
| “Oh no” / resource limit | Accidental heavy install | Keep Cloud on `requirements-streamlit.txt` only |
| Logs stop at “Spinning up manager process” | Platform issue | Reboot later; try a blank app to confirm |

Open **Manage app** (bottom-right) and read Cloud logs — that is the source of truth.

## 5. Local vs Cloud installs

```bash
# Streamlit Cloud / UI-only
pip install -r requirements.txt

# Full local stack or API host
pip install -r requirements-api.txt
```
