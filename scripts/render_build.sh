#!/usr/bin/env bash
# Render Build Command: bash scripts/render_build.sh
set -euo pipefail
python -m pip install --upgrade pip
python -m pip install -r requirements-api.txt
