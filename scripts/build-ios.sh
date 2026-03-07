#!/bin/bash
# =============================================================================
# Tesla FSD Finder - iOS Build Script
# =============================================================================
# Usage: ./scripts/build-ios.sh [--open]
#
# Prerequisites:
#   - macOS with Xcode 15+ installed
#   - Node.js 18+ and npm
#   - Apple Developer account (for device testing / App Store)
#
# This script:
#   1. Installs npm dependencies (Capacitor + plugins)
#   2. Syncs web assets to the native iOS project
#   3. Optionally opens Xcode for building/archiving
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()   { echo -e "${BLUE}[iOS Build]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# --- Pre-flight checks ---
log "Checking prerequisites..."

# macOS check
[[ "$(uname)" == "Darwin" ]] || error "iOS builds require macOS. Current OS: $(uname)"

# Xcode check
if ! command -v xcodebuild &>/dev/null; then
    error "Xcode not found. Install from the Mac App Store."
fi
XCODE_VERSION=$(xcodebuild -version | head -n1)
success "Found $XCODE_VERSION"

# Node check
if ! command -v node &>/dev/null; then
    error "Node.js not found. Install via: brew install node"
fi
NODE_VERSION=$(node --version)
success "Found Node.js $NODE_VERSION"

# CocoaPods check (needed by Capacitor iOS)
if ! command -v pod &>/dev/null; then
    warn "CocoaPods not found. Installing..."
    sudo gem install cocoapods
fi
success "Found CocoaPods $(pod --version)"

cd "$PROJECT_DIR"

# --- Step 1: Install dependencies ---
log "Installing npm dependencies..."
npm install
success "Dependencies installed"

# --- Step 2: Ensure iOS platform exists ---
if [ ! -d "ios" ] || [ ! -f "ios/App/Podfile" ]; then
    log "Adding iOS platform..."
    npx cap add ios
    success "iOS platform added"
else
    log "iOS platform already exists"
fi

# --- Step 3: Sync web assets to iOS ---
log "Syncing web assets to iOS project..."
npx cap sync ios
success "Assets synced to ios/App/"

# --- Step 4: Install CocoaPods ---
log "Installing CocoaPods dependencies..."
cd ios/App
pod install
cd "$PROJECT_DIR"
success "Pods installed"

# --- Step 5: Generate icon assets (if source exists) ---
if [ -f "assets/icon.png" ]; then
    log "Generating icon assets from assets/icon.png..."
    npx capacitor-assets generate \
        --iconBackgroundColor '#0a0e1a' \
        --splashBackgroundColor '#0a0e1a' \
        --ios
    success "Icon assets generated"
else
    warn "No assets/icon.png found. Place a 1024x1024 PNG there and re-run."
    warn "Or generate manually: npm run icons"
fi

# --- Done ---
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN} iOS project ready!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Next steps:"
echo "  1. Open in Xcode:    npx cap open ios"
echo "  2. Select your team: Xcode > App target > Signing & Capabilities"
echo "  3. Build & run:      Cmd+R (simulator) or select your device"
echo "  4. Archive for App Store: Product > Archive"
echo ""

# Optional: open Xcode
if [[ "${1:-}" == "--open" ]]; then
    log "Opening Xcode..."
    npx cap open ios
fi
