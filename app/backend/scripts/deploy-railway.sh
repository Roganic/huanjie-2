#!/bin/bash
set -e

echo "Deploying to Railway..."
echo "Prerequisites: railway CLI installed and logged in (railway login)"
echo ""

if ! command -v railway &> /dev/null; then
    echo "Error: railway CLI is not installed."
    echo "Install it with: npm install -g @railway/cli"
    exit 1
fi

if [ ! -f .env ]; then
    echo "Warning: .env not found. Make sure required variables are set in Railway dashboard:"
    echo "  - KIMI_API_KEY (or OPENAI_API_KEY)"
    echo "  - CORS_ALLOW_ORIGINS (e.g. https://yourname.github.io)"
fi

railway up

echo ""
echo "Deployment complete. Set environment variables in Railway dashboard if not already done."
