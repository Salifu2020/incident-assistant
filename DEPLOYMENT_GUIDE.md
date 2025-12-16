# Deployment Guide - Incident Assistant

This guide covers deployment options, best practices, and step-by-step instructions for deploying the Incident Assistant application.

---

## 📋 Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Deployment Options](#deployment-options)
3. [Environment Configuration](#environment-configuration)
4. [Docker Deployment](#docker-deployment)
5. [Cloud Deployment](#cloud-deployment)
6. [Security Considerations](#security-considerations)
7. [Scaling & Performance](#scaling--performance)
8. [Monitoring & Maintenance](#monitoring--maintenance)
9. [Troubleshooting](#troubleshooting)

---

## ✅ Pre-Deployment Checklist

Before deploying, ensure you have:

- [ ] **Python 3.8+** installed
- [ ] **Ollama** running and accessible (for LLM)
- [ ] **ChromaDB** storage directory configured
- [ ] **Environment variables** set (see below)
- [ ] **API keys** configured (if using external services)
- [ ] **Database backups** configured (if using external DB)
- [ ] **SSL certificates** (for production HTTPS)
- [ ] **Firewall rules** configured
- [ ] **Monitoring tools** set up

---

## 🚀 Deployment Options

### Option 1: Local/On-Premise Deployment

**Best for:** Development, testing, or small teams

**Requirements:**
- Server with Python 3.8+
- Sufficient RAM (8GB+ recommended)
- Storage for documents and ChromaDB

**Steps:**
```bash
# 1. Clone repository
git clone https://github.com/Salifu2020/incident-assistant
cd incident-assistant

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env with your settings

# 5. Start Ollama (if not already running)
ollama serve

# 6. Run API server
python run_api.py

# 7. Run Streamlit frontend (in another terminal)
python run_app.py
```

---

### Option 2: Docker Deployment (Recommended)

**Best for:** Production, consistent environments, easy scaling

#### Create Dockerfile

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p data logs .chromadb ingested_files source_files

# Expose ports
EXPOSE 8000 8501

# Start Ollama and API
CMD ["sh", "-c", "ollama serve & python run_api.py"]
```

#### Create docker-compose.yml

```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - OLLAMA_HOST=http://ollama:11434
      - ENVIRONMENT=production
      - SECRET_KEY=${SECRET_KEY}
    volumes:
      - ./data:/app/data
      - ./.chromadb:/app/.chromadb
      - ./ingested_files:/app/ingested_files
      - ./logs:/app/logs
    depends_on:
      - ollama
    restart: unless-stopped

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    restart: unless-stopped

  frontend:
    build: .
    command: streamlit run src/app.py --server.port=8501 --server.address=0.0.0.0
    ports:
      - "8501:8501"
    environment:
      - API_URL=http://api:8000
    depends_on:
      - api
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - api
      - frontend
    restart: unless-stopped

volumes:
  ollama_data:
```

#### Deploy with Docker

```bash
# Build and start services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

---

### Option 3: Cloud Deployment

#### A. AWS Deployment

**Using EC2:**
1. Launch EC2 instance (Ubuntu 22.04, t3.medium or larger)
2. Install Docker and Docker Compose
3. Clone repository
4. Configure security groups (ports 80, 443, 8000, 8501)
5. Set up Elastic IP
6. Deploy using docker-compose

**Using ECS/Fargate:**
1. Create ECR repository
2. Build and push Docker image
3. Create ECS task definition
4. Create ECS service
5. Configure Application Load Balancer

**Using Elastic Beanstalk:**
```bash
# Install EB CLI
pip install awsebcli

# Initialize EB
eb init -p docker incident-assistant

# Create environment
eb create production-env

# Deploy
eb deploy
```

#### B. Google Cloud Platform (GCP)

**Using Cloud Run:**
```bash
# Build and push to GCR
gcloud builds submit --tag gcr.io/PROJECT_ID/incident-assistant

# Deploy to Cloud Run
gcloud run deploy incident-assistant \
  --image gcr.io/PROJECT_ID/incident-assistant \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

**Using Compute Engine:**
Similar to AWS EC2 deployment

#### C. Azure Deployment

**Using Azure Container Instances:**
```bash
# Build and push to ACR
az acr build --registry REGISTRY_NAME --image incident-assistant:latest .

# Deploy to ACI
az container create \
  --resource-group RESOURCE_GROUP \
  --name incident-assistant \
  --image REGISTRY_NAME.azurecr.io/incident-assistant:latest \
  --ports 8000 8501
```

**Using Azure App Service:**
1. Create App Service plan
2. Create Web App
3. Configure deployment from container registry
4. Set environment variables
5. Deploy

#### D. Heroku Deployment

```bash
# Install Heroku CLI
# Create Procfile
echo "web: uvicorn src.api:app --host 0.0.0.0 --port \$PORT" > Procfile
echo "worker: streamlit run src/app.py --server.port \$PORT" >> Procfile

# Login to Heroku
heroku login

# Create app
heroku create incident-assistant

# Set environment variables
heroku config:set SECRET_KEY=your-secret-key
heroku config:set OLLAMA_HOST=https://your-ollama-instance.com

# Deploy
git push heroku main
```

---

## ⚙️ Environment Configuration

### Required Environment Variables

Create a `.env` file:

```env
# Application
ENVIRONMENT=production
SECRET_KEY=your-secret-key-here-change-in-production
DEBUG=False

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_URL=http://localhost:8000

# Frontend Configuration
STREAMLIT_PORT=8501
STREAMLIT_SERVER_ADDRESS=0.0.0.0

# Ollama Configuration
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=mistral

# Database/Storage
CHROMADB_PATH=./.chromadb
DATA_DIR=./data
INGESTED_FILES_DIR=./ingested_files
SOURCE_FILES_DIR=./source_files

# Embedding Model
EMBEDDING_MODEL=all-mpnet-base-v2

# Security
ALLOWED_ORIGINS=http://localhost:8501,https://yourdomain.com
CORS_ENABLED=True

# Authentication (if enabled)
JWT_SECRET_KEY=your-jwt-secret
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# Email Configuration (if using email features)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=noreply@yourdomain.com

# Logging
LOG_LEVEL=INFO
LOG_FILE=./logs/api.log
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5
```

### Production Security Checklist

- [ ] Change all default passwords and secrets
- [ ] Use strong, randomly generated SECRET_KEY
- [ ] Enable HTTPS/SSL
- [ ] Configure CORS properly
- [ ] Set up firewall rules
- [ ] Enable rate limiting
- [ ] Configure authentication (if not already enabled)
- [ ] Set up regular backups
- [ ] Enable logging and monitoring
- [ ] Review and restrict file upload permissions

---

## 🔒 Security Considerations

### 1. API Security

```python
# Add to src/api.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/ask")
@limiter.limit("10/minute")  # Rate limit
async def ask_question(request: Request, payload: QuestionRequest):
    # ... existing code
```

### 2. File Upload Security

- Validate file types and sizes
- Scan uploads for malware
- Store uploads outside web root
- Use secure file names

### 3. Database Security

- Use connection encryption
- Restrict database access
- Regular backups
- Access logging

### 4. Network Security

- Use HTTPS/TLS
- Configure firewall rules
- Use VPN for admin access
- Implement DDoS protection

---

## 📈 Scaling & Performance

### Horizontal Scaling

**Load Balancer Configuration (Nginx):**

```nginx
# nginx.conf
upstream api_backend {
    least_conn;
    server api1:8000;
    server api2:8000;
    server api3:8000;
}

upstream frontend_backend {
    least_conn;
    server frontend1:8501;
    server frontend2:8501;
}

server {
    listen 80;
    server_name yourdomain.com;
    
    location /api/ {
        proxy_pass http://api_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    location / {
        proxy_pass http://frontend_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Vertical Scaling

- Increase server RAM for larger knowledge bases
- Use faster CPUs for embedding generation
- SSD storage for ChromaDB
- More powerful GPU for Ollama (optional)

### Caching Strategy

- Cache document embeddings
- Cache query suggestions
- Cache translations
- Use Redis for distributed caching

### Database Optimization

- Index frequently queried fields
- Regular ChromaDB optimization
- Archive old documents
- Partition large collections

---

## 📊 Monitoring & Maintenance

### Health Checks

The application includes health monitoring endpoints:

```bash
# Health check
curl http://localhost:8000/health

# Metrics
curl http://localhost:8000/metrics
```

### Logging

Logs are stored in:
- `logs/api.log` - API server logs
- `logs/streamlit.log` - Frontend logs

### Monitoring Tools

**Recommended:**
- **Prometheus + Grafana** for metrics
- **Sentry** for error tracking
- **ELK Stack** for log aggregation
- **Uptime monitoring** (UptimeRobot, Pingdom)

### Backup Strategy

```bash
# Backup ChromaDB
tar -czf chromadb-backup-$(date +%Y%m%d).tar.gz .chromadb/

# Backup uploaded files
tar -czf files-backup-$(date +%Y%m%d).tar.gz ingested_files/ source_files/

# Backup configuration
cp .env .env.backup
```

**Automated Backup Script:**

```bash
#!/bin/bash
# backup.sh
BACKUP_DIR="/backups/incident-assistant"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup ChromaDB
tar -czf $BACKUP_DIR/chromadb-$DATE.tar.gz .chromadb/

# Backup files
tar -czf $BACKUP_DIR/files-$DATE.tar.gz ingested_files/ source_files/

# Backup data
tar -czf $BACKUP_DIR/data-$DATE.tar.gz data/

# Keep only last 7 days
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete
```

Add to crontab:
```bash
0 2 * * * /path/to/backup.sh
```

---

## 🔧 Troubleshooting

### Common Issues

**1. Ollama Connection Error**
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Restart Ollama
ollama serve
```

**2. ChromaDB Lock Error**
```bash
# Remove lock file
rm .chromadb/chroma.sqlite3-wal
rm .chromadb/chroma.sqlite3-shm
```

**3. Port Already in Use**
```bash
# Find process using port
lsof -i :8000
# Kill process
kill -9 <PID>
```

**4. Memory Issues**
- Reduce `max_context_chars`
- Use smaller embedding model
- Limit concurrent requests
- Increase server RAM

**5. Slow Response Times**
- Enable caching
- Use faster embedding model
- Optimize ChromaDB
- Scale horizontally

---

## 📝 Deployment Checklist

### Pre-Deployment
- [ ] Code review completed
- [ ] Tests passing
- [ ] Environment variables configured
- [ ] Secrets rotated
- [ ] SSL certificates ready
- [ ] Database backups configured
- [ ] Monitoring set up

### Deployment
- [ ] Deploy to staging first
- [ ] Run smoke tests
- [ ] Verify all endpoints
- [ ] Check logs for errors
- [ ] Monitor performance
- [ ] Deploy to production
- [ ] Verify production deployment

### Post-Deployment
- [ ] Monitor error rates
- [ ] Check response times
- [ ] Verify backups running
- [ ] Review security logs
- [ ] Update documentation
- [ ] Notify team

---

## 🚀 Quick Start Deployment

### Minimal Production Setup

```bash
# 1. Clone and setup
git clone https://github.com/Salifu2020/incident-assistant
cd incident-assistant
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with production values

# 3. Start Ollama
ollama serve &

# 4. Start API with production server
gunicorn src.api:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000

# 5. Start Frontend (in separate terminal)
streamlit run src/app.py --server.port=8501 --server.address=0.0.0.0
```

### With Systemd (Linux)

**Create `/etc/systemd/system/incident-assistant-api.service`:**
```ini
[Unit]
Description=Incident Assistant API
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/incident-assistant
Environment="PATH=/opt/incident-assistant/.venv/bin"
ExecStart=/opt/incident-assistant/.venv/bin/gunicorn src.api:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
Restart=always

[Install]
WantedBy=multi-user.target
```

**Enable and start:**
```bash
sudo systemctl enable incident-assistant-api
sudo systemctl start incident-assistant-api
```

---

## 📚 Additional Resources

- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
- [Streamlit Deployment](https://docs.streamlit.io/streamlit-community-cloud/deploy-your-app)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [Ollama Documentation](https://github.com/ollama/ollama)

---

## 💡 Next Steps

After deployment:
1. Set up monitoring and alerts
2. Configure automated backups
3. Implement CI/CD pipeline
4. Set up staging environment
5. Document runbooks
6. Train team on operations

---

**Need Help?** Open an issue on GitHub or contact the development team.

