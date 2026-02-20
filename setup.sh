#!/usr/bin/env bash
#
# setup.sh — One-time setup for developers cloning the repo.
# Installs git hooks, Python dependencies, and fetches initial dataset.
#
set -e

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Anti-MicroStrategy Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. Install Python dependencies
echo "[1/4] Installing Python dependencies..."
pip install -r "${REPO_ROOT}/requirements.txt" --quiet 2>/dev/null || {
    pip3 install -r "${REPO_ROOT}/requirements.txt" --quiet 2>/dev/null || {
        echo "  ⚠ Could not install dependencies. Run manually: pip install -r requirements.txt"
    }
}
echo "  Done."

# 2. Install git hooks
echo "[2/4] Installing git hooks..."
HOOKS_DIR="${REPO_ROOT}/.git/hooks"
mkdir -p "${HOOKS_DIR}"

# Copy hooks from hooks/ directory
for hook in "${REPO_ROOT}/hooks/"*; do
    hook_name="$(basename "${hook}")"
    cp "${hook}" "${HOOKS_DIR}/${hook_name}"
    chmod +x "${HOOKS_DIR}/${hook_name}"
    echo "  Installed: ${hook_name}"
done
echo "  Done."

# 3. Check for Claude CLI
echo "[3/4] Checking for Claude Code CLI..."
if command -v claude &> /dev/null; then
    CLAUDE_VERSION=$(claude --version 2>/dev/null || echo "unknown")
    echo "  Found: claude ${CLAUDE_VERSION}"
else
    echo "  ⚠ Claude Code CLI not found."
    echo "    Install: npm install -g @anthropic-ai/claude-code"
    echo "    The backtest will use rule-based fallback until Claude is available."
fi

# 4. Fetch initial dataset (if not present)
echo "[4/4] Checking for dataset..."
if [ ! -f "${REPO_ROOT}/datasets/latest.json" ]; then
    echo "  Fetching 30-day BTC dataset from Deribit..."
    cd "${REPO_ROOT}" && python3 -m backtest.fetch_dataset 2>/dev/null || {
        echo "  ⚠ Could not fetch dataset. Run manually: python -m backtest.fetch_dataset"
    }
else
    echo "  Dataset already exists. Use --fetch to re-download."
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup complete!"
echo ""
echo "  Next steps:"
echo "    1. Run a backtest:  python -m backtest.run_backtest"
echo "    2. For live trading: cp .env.example .env && edit .env"
echo "    3. Live trading:    python run.py"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
