#!/usr/bin/env python
"""Entry point for running the FastAPI server."""
import uvicorn

if __name__ == "__main__":
    import os
    uvicorn.run(
        "src.api:app",
        host="127.0.0.1",
        port=8000,
        # Default to no auto-reload because it can drop active SSE streams ("Response ended prematurely").
        # Set UVICORN_RELOAD=1 for dev auto-reload.
        reload=os.environ.get("UVICORN_RELOAD", "0") == "1",
        timeout_keep_alive=75,  # Keep connections alive longer for slow requests
        timeout_graceful_shutdown=10
    )

