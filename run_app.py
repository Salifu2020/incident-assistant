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
        load_dotenv()
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
