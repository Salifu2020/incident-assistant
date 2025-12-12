#!/usr/bin/env python
"""Entry point for running the Streamlit frontend."""
import subprocess
import sys
import os

if __name__ == "__main__":
    app_path = os.path.join(os.path.dirname(__file__), "src", "app.py")
    # Convert to absolute path for cross-platform compatibility
    app_path = os.path.abspath(app_path)
    subprocess.run([sys.executable, "-m", "streamlit", "run", app_path])

