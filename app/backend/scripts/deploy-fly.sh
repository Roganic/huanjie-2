#!/bin/bash
set -e

echo "Deploying to Fly.io..."
echo "Prerequisites: flyctl installed and logged in (fly auth login)"
echo ""

if ! command -v flyctl &> /dev/null; then
    echo "Error: flyctl is not installed."
    echo "Install it with: curl -L https://fly.io/install.sh | sh"
    exit 1
fi

if [ ! -f fly.toml ]; then
    echo "Error: fly.toml not found in current directory."
    echo "Run this script from app/backend/"
    exit 1
fi

flyctl deploy

echo ""
echo "Deployment complete."
echo "Set secrets with: flyctl secrets set KIMI_API_KEY=xxx CORS_ALLOW_ORIGINS=https://yourname.github.io"
