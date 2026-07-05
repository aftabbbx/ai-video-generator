#!/bin/bash

# VividFlow Setup & Startup Script
# Optimized for Apple Silicon (M1/M2/M3/M4) macOS systems

# Colors for pretty terminal output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${PURPLE}====================================================${NC}"
echo -e "${PURPLE}       VividFlow: Local AI Video Generator          ${NC}"
echo -e "${PURPLE}====================================================${NC}"
echo -e "${BLUE}[*] Initializing environment setup...${NC}"

# Check python3
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[!] Error: python3 is not installed on this system.${NC}"
    echo -e "${YELLOW}Please install Python 3.9+ (e.g. via Homebrew: 'brew install python') and try again.${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo -e "${GREEN}[+] Found Python ${PYTHON_VERSION}${NC}"

# Get directory where script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo -e "${BLUE}[*] Creating Python virtual environment (venv)...${NC}"
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo -e "${RED}[!] Error: Failed to create virtual environment.${NC}"
        exit 1
    fi
    echo -e "${GREEN}[+] Virtual environment created successfully.${NC}"
fi

# Activate virtual environment
echo -e "${BLUE}[*] Activating virtual environment...${NC}"
source venv/bin/activate

# Upgrade pip
echo -e "${BLUE}[*] Upgrading pip...${NC}"
pip install --upgrade pip

# Install requirements
echo -e "${BLUE}[*] Installing python dependencies (this can take a few minutes on first run)...${NC}"
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo -e "${RED}[!] Error: Dependency installation failed.${NC}"
    exit 1
fi
echo -e "${GREEN}[+] Dependencies successfully installed.${NC}"

# Check if user wants to run a quick test
if [ "$1" == "--test" ]; then
    echo -e "${YELLOW}[*] Running local generation test to check PyTorch/MPS compatibility...${NC}"
    python3 -m backend.generator --test
    exit $?
fi

# Launch app and open in browser
echo -e "${BLUE}[*] Starting VividFlow local FastAPI server...${NC}"
echo -e "${GREEN}[+] Web UI will open automatically at: ${YELLOW}http://127.0.0.1:8000${NC}"
echo -e "${BLUE}[*] Press Ctrl+C to stop the server.${NC}"

# Open browser after a short delay to let the server start
(sleep 2.5 && open http://127.0.0.1:8000) &

# Run server
python3 -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
