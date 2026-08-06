#!/usr/bin/env bash
# Exit on error
set -o errexit

echo "=== Fallen Officer Memorial System Render Build Script ==="
python -m pip install --upgrade pip
pip install -r requirements.txt

# Create data directory if local
mkdir -p /var/data || true

echo "=== Build Complete ==="
