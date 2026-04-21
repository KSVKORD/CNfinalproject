#!/bin/bash
# setup.sh — Run inside WSL2 Ubuntu.
# Installs Node.js (via nvm), FFmpeg, and project dependencies.
# Then copies the project to ~/netstream for better FFmpeg I/O performance.

set -e  # stop on any error

PROJECT_WIN="/mnt/c/Users/$USER/Desktop/Projects/CN_Finalpj"
PROJECT_WSL="$HOME/netstream"

echo "=== NetStream environment setup ==="

# 1. Confirm WSL2 kernel (not WSL1)
if [ ! -f /proc/version ] || ! grep -qi microsoft /proc/version; then
    echo "ERROR: Not running inside WSL. Run this script from a WSL2 Ubuntu terminal." >&2
    exit 1
fi

# 2. Install nvm if not present
if ! command -v nvm &>/dev/null && [ ! -d "$HOME/.nvm" ]; then
    echo "[1/4] Installing nvm..."
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
fi
# Load nvm for this session
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"

# 3. Install Node.js LTS
echo "[2/4] Installing Node.js LTS..."
nvm install --lts
nvm use --lts
echo "Node.js: $(node --version)"

# 4. Install FFmpeg
echo "[3/4] Installing FFmpeg..."
sudo apt-get update -q && sudo apt-get install -y -q ffmpeg
echo "FFmpeg: $(ffmpeg -version 2>&1 | head -1)"

# 5. Copy project to WSL2 native filesystem (better I/O for FFmpeg)
echo "[4/4] Copying project to $PROJECT_WSL..."
if [ -d "$PROJECT_WSL" ]; then
    echo "  $PROJECT_WSL already exists — skipping copy."
else
    if [ -d "$PROJECT_WIN" ]; then
        cp -r "$PROJECT_WIN" "$PROJECT_WSL"
        echo "  Copied from $PROJECT_WIN"
    else
        echo "  WARNING: Windows project path not found. Running npm install in current directory."
        PROJECT_WSL="$(pwd)"
    fi
fi

# 6. Install Node.js dependencies
cd "$PROJECT_WSL"
echo "Installing npm packages..."
npm install
echo ""
echo "=== Setup complete ==="
echo "To start the server:"
echo "  cd $PROJECT_WSL && node server.js"
echo ""
echo "Open http://localhost:3000 in Windows Chrome to verify."
