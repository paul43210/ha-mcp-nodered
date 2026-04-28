#!/usr/bin/env bash
#
# deploy.sh — restart ha-mcp-nodered.service and health-check it.
#
# Assumes:
#   - /etc/ha-mcp-nodered/env exists (chmod 600, owned by AIScripts)
#   - /etc/systemd/system/ha-mcp-nodered.service is installed and enabled
#   - build.sh has been run since the last git pull

set -euo pipefail

SERVICE="ha-mcp-nodered.service"
ENV_FILE="/etc/ha-mcp-nodered/env"
HEALTH_TIMEOUT=20

log() { printf '%s [deploy] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { printf '%s [deploy] ERROR: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; exit 1; }

[[ -r "$ENV_FILE" ]] || die "$ENV_FILE missing or unreadable"

# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a

PORT="${MCP_PORT:-8086}"
SECRET_PATH="${MCP_SECRET_PATH:-/mcp}"

log "restarting $SERVICE"
sudo systemctl restart "$SERVICE"

log "waiting up to ${HEALTH_TIMEOUT}s for service to listen on 127.0.0.1:${PORT}"
deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
until ss -ltn "sport = :${PORT}" | grep -q ":${PORT}"; do
    if (( $(date +%s) > deadline )); then
        log "service did not bind to port within ${HEALTH_TIMEOUT}s"
        log "last 30 lines of journal:"
        sudo journalctl -u "$SERVICE" -n 30 --no-pager
        die "deployment failed: port ${PORT} never opened"
    fi
    sleep 1
done

log "probing http://127.0.0.1:${PORT}${SECRET_PATH}"
http_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
    "http://127.0.0.1:${PORT}${SECRET_PATH}" || echo "000")

case "$http_code" in
    200|404|405|406)
        log "health check passed (HTTP $http_code) — service is responding"
        ;;
    *)
        log "health check FAILED (HTTP $http_code)"
        log "last 30 lines of journal:"
        sudo journalctl -u "$SERVICE" -n 30 --no-pager
        die "deployment failed: unexpected HTTP $http_code"
        ;;
esac

log "deployment OK — $SERVICE listening on 127.0.0.1:${PORT}${SECRET_PATH}"
sudo systemctl status "$SERVICE" --no-pager -n 5 || true
