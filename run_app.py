#!/usr/bin/env python
"""Start the Streamlit frontend. Usage: python run_app.py"""
import os
import sys
import subprocess

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def _load_dotenv():
    try:
        from dotenv import load_dotenv
        # This repo uses `.env.local` (not `.env`) for secrets.
        # Load it explicitly so LLM/Groq selection works in all run modes.
        project_root = os.path.dirname(os.path.abspath(__file__))
        env_local = os.path.join(project_root, ".env.local")
        if os.path.exists(env_local):
            # Keep shell/session env vars (e.g., API_URL) higher priority than file defaults.
            load_dotenv(dotenv_path=env_local, override=False)
        else:
            load_dotenv(override=False)
    except ImportError:
        pass

def main():
    _load_dotenv()
    app_path = os.path.join(os.path.dirname(__file__), "src", "app.py")
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        os.path.abspath(app_path),
    ])

if __name__ == "__main__":
    main()
