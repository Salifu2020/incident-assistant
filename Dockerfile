# Multi-stage Dockerfile for Incident Assistant (Optimized for size)
# Stage 1: Build dependencies
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies to a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies (this stage can be large, but won't be in final image)
# Prevent model downloads during build - models will download at runtime
ENV TRANSFORMERS_OFFLINE=1
ENV HF_HUB_OFFLINE=1
ENV SENTENCE_TRANSFORMERS_HOME=/tmp  # Temporary location, won't be in final image
# Install dependencies and clean up any accidentally downloaded models
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    rm -rf /root/.cache/huggingface /root/.cache/torch /tmp/.cache 2>/dev/null || true

# Stage 2: Runtime image (much smaller)
FROM python:3.11-slim

WORKDIR /app

# Install only runtime dependencies (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder, but exclude model caches
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Remove any model caches that might have been downloaded during pip install
# (Don't remove the packages themselves, just cached models)
RUN rm -rf /opt/venv/lib/python*/site-packages/*/models 2>/dev/null || true && \
    rm -rf /opt/venv/lib/python*/site-packages/sentence_transformers/.cache 2>/dev/null || true && \
    rm -rf /root/.cache /tmp/.cache /tmp/sentence-transformers 2>/dev/null || true

# Copy application code (only what's needed)
COPY src/ ./src/
COPY run_api.py .
COPY run_cli.py .

# Create necessary directories
RUN mkdir -p data logs .chromadb ingested_files source_files

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
# Models will be downloaded at runtime, not at build time (saves GBs)
# Clear offline flags to allow runtime downloads
ENV TRANSFORMERS_OFFLINE=0
ENV HF_HUB_OFFLINE=0
ENV TRANSFORMERS_CACHE=/app/.cache/transformers
ENV SENTENCE_TRANSFORMERS_HOME=/app/.cache/sentence-transformers
# Use lighter model by default to reduce download size
ENV EMBEDDING_MODEL=all-MiniLM-L6-v2

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command
CMD ["python", "run_api.py"]


