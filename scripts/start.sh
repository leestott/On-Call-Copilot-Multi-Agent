#!/usr/bin/env bash
# On-Call Copilot — Startup Script (Bash)
# Usage:
#   bash scripts/start.sh                # Start both agent server + UI
#   bash scripts/start.sh --skip-ui      # Start agent server only
#   bash scripts/start.sh --mock         # Start in mock mode (no Azure needed)
#   bash scripts/start.sh --skip-install # Skip pip install step

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

SKIP_UI=false
MOCK_MODE=false
SKIP_INSTALL=false

for arg in "$@"; do
    case "$arg" in
        --skip-ui)      SKIP_UI=true ;;
        --mock)         MOCK_MODE=true ;;
        --skip-install) SKIP_INSTALL=true ;;
        *) echo "Unknown option: $arg"; exit 1 ;;
    esac
done

# ─── preflight checks ────────────────────────────────────────────────────────

echo ""
echo "=== On-Call Copilot — Startup ==="

# Python
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then PYTHON="$cmd"; break; fi
done
if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.10+ is required. Install from https://python.org"
    exit 1
fi
echo "[check] $($PYTHON --version)"

# Azure CLI (skip in mock mode)
if [ "$MOCK_MODE" = false ]; then
    if ! command -v az &>/dev/null; then
        echo "ERROR: Azure CLI is required. Install from https://aka.ms/install-az-cli"
        exit 1
    fi
    echo "[check] Azure CLI found"
fi

# ─── virtual environment ─────────────────────────────────────────────────────

if [ ! -d ".venv" ]; then
    echo ""
    echo "[setup] Creating virtual environment..."
    $PYTHON -m venv .venv
fi

source .venv/bin/activate
echo "[check] Virtual environment activated"

# ─── dependencies ────────────────────────────────────────────────────────────

if [ "$SKIP_INSTALL" = false ]; then
    echo ""
    echo "[setup] Installing dependencies..."
    pip install -r requirements.txt --quiet
    echo "[check] Dependencies installed"
else
    echo "[skip]  Dependency install skipped"
fi

# ─── environment file ────────────────────────────────────────────────────────

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "[setup] Created .env from .env.example — edit it with your Azure values"
        exit 1
    else
        echo "WARNING: No .env file found. Set environment variables manually."
    fi
fi

# ─── azure login check (skip in mock mode) ───────────────────────────────────

if [ "$MOCK_MODE" = false ]; then
    if ! az account show &>/dev/null; then
        echo ""
        echo "[auth] Not signed in to Azure. Running 'az login'..."
        TENANT_ID=""
        if [ -f ".env" ]; then
            TENANT_ID=$(grep -E "^AZURE_TENANT_ID=" .env | cut -d'=' -f2 | tr -d '"'"'" || true)
        fi
        if [ -n "$TENANT_ID" ]; then
            az login --tenant "$TENANT_ID"
        else
            az login
        fi
    fi
    echo "[check] Azure CLI authenticated"
fi

# ─── cleanup function ────────────────────────────────────────────────────────

cleanup() {
    echo ""
    echo "[stop] Shutting down..."
    if [ -n "${AGENT_PID:-}" ]; then
        kill "$AGENT_PID" 2>/dev/null || true
        wait "$AGENT_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

# ─── start servers ───────────────────────────────────────────────────────────

if [ "$MOCK_MODE" = true ]; then
    echo ""
    echo "[start] Launching mock server (no Azure needed)..."
    MOCK_MODE=true $PYTHON -m app.main
elif [ "$SKIP_UI" = true ]; then
    echo ""
    echo "[start] Launching agent server on http://localhost:8088 ..."
    $PYTHON main.py
else
    echo ""
    echo "[start] Launching agent server on http://localhost:8088 ..."
    echo "[start] Launching UI server on http://localhost:7860 ..."
    echo "[info]  Press Ctrl+C to stop both servers."
    echo ""

    $PYTHON main.py &
    AGENT_PID=$!

    # Small delay so the agent server begins listening before the UI connects
    sleep 3

    $PYTHON ui/server.py
fi
