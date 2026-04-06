#!/usr/bin/env python
"""Start the FastAPI backend. Usage: python run_api.py"""
import os
import sys

# Ensure Windows console stdout/stderr can handle unicode safely.
# This prevents UnicodeEncodeError ('charmap' codec) from breaking request handling.
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def _load_dotenv():
    try:
        from dotenv import load_dotenv
        # This repo uses `.env.local` (not `.env`) for secrets.
        project_root = os.path.dirname(os.path.abspath(__file__))
        env_local = os.path.join(project_root, ".env.local")
        if os.path.exists(env_local):
            # Keep shell/session env vars (e.g., PORT) higher priority than file defaults.
            load_dotenv(dotenv_path=env_local, override=False)
        else:
            load_dotenv(override=False)
    except ImportError:
        pass

def main():
    _load_dotenv()
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run(
        "src.api:app",
        host=host,
        port=port,
        reload=os.environ.get("UVICORN_RELOAD", "0") == "1",
        timeout_keep_alive=75,
        timeout_graceful_shutdown=10,
    )

if __name__ == "__main__":
    main()
