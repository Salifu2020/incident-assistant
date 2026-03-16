#!/usr/bin/env python
"""Unified entry point for Incident Assistant. Usage: python run.py [api|app|cli]"""
import os
import sys
import subprocess

def _load_dotenv():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

def run_api():
    """Start the FastAPI server."""
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

def run_app():
    """Start the Streamlit frontend."""
    app_path = os.path.join(os.path.dirname(__file__), "src", "app.py")
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        os.path.abspath(app_path),
    ])

def run_cli():
    """Start the CLI interface."""
    from src.cli import main
    main()

def main():
    commands = {"api": run_api, "app": run_app, "cli": run_cli}
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "api").lower()
    if cmd not in commands:
        print(f"Usage: python run.py [api|app|cli]")
        print(f"  api  - Start FastAPI backend")
        print(f"  app  - Start Streamlit frontend")
        print(f"  cli  - Start CLI interface")
        sys.exit(1)
    commands[cmd]()

if __name__ == "__main__":
    main()
