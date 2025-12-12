#!/usr/bin/env python
"""Entry point for running the FastAPI server."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("src.api:app", host="127.0.0.1", port=8000, reload=True)

