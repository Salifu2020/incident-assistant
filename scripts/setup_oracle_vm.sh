#!/bin/bash
# Setup script for Oracle Cloud Always Free VM
# Run as: bash setup_oracle_vm.sh
# Works on Oracle Linux 8 and Ubuntu 22.04

set -e

echo "=== Incident Assistant - Oracle Cloud VM Setup ==="

# Detect OS
if [ -f /etc/oracle-release ]; then
    OS="oracle"
elif [ -f /etc/debian_version ]; then
    OS="ubuntu"
else
    echo "Unsupported OS. This script supports Oracle Linux and Ubuntu."
    exit 1
fi

echo "Detected OS: $OS"

# Update system
echo "Updating system..."
if [ "$OS" = "oracle" ]; then
    sudo dnf update -y
elif [ "$OS" = "ubuntu" ]; then
    sudo apt update && sudo apt upgrade -y
fi

# Install Docker
echo "Installing Docker..."
if [ "$OS" = "oracle" ]; then
    sudo dnf install -y docker
elif [ "$OS" = "ubuntu" ]; then
    sudo apt install -y docker.io
fi

sudo systemctl enable docker
sudo systemctl start docker

# Add current user to docker group
sudo usermod -aG docker "$USER"

# Install Docker Compose
echo "Installing Docker Compose..."
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Install git if missing
if ! command -v git &> /dev/null; then
    echo "Installing git..."
    if [ "$OS" = "oracle" ]; then
        sudo dnf install -y git
    else
        sudo apt install -y git
    fi
fi

echo ""
echo "=== Setup complete ==="
echo "1. Log out and log back in (or run: newgrp docker) for group changes to take effect"
echo "2. Create .env with SECRET_KEY (and optional LLM_MODEL, EMBEDDING_MODEL)"
echo "3. Run: docker compose -f docker-compose.oracle.yml up -d"
echo ""
echo "See DEPLOY_ORACLE_CLOUD.md for full instructions."
