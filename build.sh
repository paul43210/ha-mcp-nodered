#!/usr/bin/env bash
#
# build.sh — build ha-mcp-nodered's production venv via uv.
#
# Run after every git pull. Sets up .venv with production deps only.
# For dev work (lint/typecheck/tests), use `uv sync --group dev` instead.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { printf '%s [build] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { printf '%s [build] ERROR: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; exit 1; }

export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null || die "uv not on PATH (install: https://astral.sh/uv)"

cd "$REPO_DIR"

log "uv sync (production deps only — no --group dev)"
uv sync --no-dev

log "smoke test: uv run ha-mcp-nodered --version"
uv run ha-mcp-nodered --version

log "build complete"
