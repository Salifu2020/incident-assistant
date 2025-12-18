#!/bin/bash
# Deployment script for Incident Assistant
# Usage: ./deploy.sh [environment]

set -e

ENVIRONMENT=${1:-production}
echo "🚀 Deploying Incident Assistant to $ENVIRONMENT environment..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from .env.example..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✅ Created .env file. Please update it with your configuration."
        exit 1
    else
        echo "❌ .env.example not found. Please create .env manually."
        exit 1
    fi
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p data logs .chromadb ingested_files source_files ssl

# Build Docker images
echo "🔨 Building Docker images..."
docker-compose build

# Pull latest Ollama image
echo "📥 Pulling Ollama image..."
docker-compose pull ollama

# Start services
echo "🚀 Starting services..."
docker-compose up -d

# Wait for services to be healthy
echo "⏳ Waiting for services to start..."
sleep 10

# Check service health
echo "🏥 Checking service health..."
if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ API service is healthy"
else
    echo "⚠️  API service health check failed"
fi

# Show running containers
echo "📊 Running containers:"
docker-compose ps

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📝 Services:"
echo "  - API: http://localhost:8000"
echo "  - Frontend: http://localhost:8501"
echo "  - Ollama: http://localhost:11434"
echo ""
echo "📋 Useful commands:"
echo "  - View logs: docker-compose logs -f"
echo "  - Stop services: docker-compose down"
echo "  - Restart services: docker-compose restart"
echo "  - Update deployment: git pull && ./deploy.sh"


