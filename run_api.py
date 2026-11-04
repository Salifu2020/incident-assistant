#!/usr/bin/env python
"""Start the FastAPI backend. Usage: python run_api.py"""
import os
import subprocess
import sys

# Ensure Windows console stdout/stderr can handle unicode safely.
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

# Add project root to path
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def _load_dotenv():
    try:
        from dotenv import load_dotenv
        env_local = os.path.join(ROOT, ".env.local")
        if os.path.exists(env_local):
            load_dotenv(dotenv_path=env_local, override=False)
        else:
            load_dotenv(override=False)
    except ImportError:
        pass


def _ensure_api_deps() -> None:
    """Install API deps if the build used Streamlit-only requirements.txt."""
    try:
        import fastapi  # noqa: F401
        return
    except ImportError:
        pass

    req = os.path.join(ROOT, "requirements-api.txt")
    print(
        "fastapi missing — installing requirements-api.txt.\n"
        "Fix permanently in Render → Settings:\n"
        "  Build Command: pip install -r requirements-api.txt\n"
        "  Start Command: python run_api.py\n",
        flush=True,
    )
    if not os.path.isfile(req):
        print(f"ERROR: {req} not found", flush=True)
        sys.exit(1)
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", req],
        check=False,
    )
    if result.returncode != 0:
        print("ERROR: pip install -r requirements-api.txt failed", flush=True)
        sys.exit(result.returncode)
    try:
        import fastapi  # noqa: F401
    except ImportError:
        print("ERROR: fastapi still missing after install", flush=True)
        sys.exit(1)


def main():
    _load_dotenv()
    _ensure_api_deps()
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
