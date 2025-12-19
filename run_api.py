#!/usr/bin/env python
"""Entry point for running the FastAPI server."""
import uvicorn

if __name__ == "__main__":
    import os
    # Railway provides PORT environment variable
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run(
        "src.api:app",
        host=host,
        port=port,
        # Default to no auto-reload because it can drop active SSE streams ("Response ended prematurely").
        # Set UVICORN_RELOAD=1 for dev auto-reload.
        reload=os.environ.get("UVICORN_RELOAD", "0") == "1",
        timeout_keep_alive=75,  # Keep connections alive longer for slow requests
        timeout_graceful_shutdown=10
    )

