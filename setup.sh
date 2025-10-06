#!/bin/bash

# Project Chimera Setup Script
echo "=================================================="
echo "     Project Chimera - Discord Bot Setup"
echo "=================================================="

# Check Python version
echo -n "Checking Python version... "
python_version=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
required_version="3.11"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" = "$required_version" ]; then
    echo "✓ Python $python_version"
else
    echo "✗ Python $python_version (requires 3.11+)"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment exists"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Install/upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip > /dev/null 2>&1

# Install requirements
echo "Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file and add your Discord bot token"
echo "2. Activate the virtual environment: source .venv/bin/activate"
echo "3. Run the bot: python main.py"
echo ""
echo "For development with hot reload:"
echo "  watchmedo auto-restart -d src -p '*.py' -- python main.py"