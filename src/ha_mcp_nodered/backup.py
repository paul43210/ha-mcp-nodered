"""Automatic flow backups taken before every destructive write.

Every write tool in this server ends in `POST /flows`, which replaces the
entire flow array. Node-RED keeps its own `.flows.json.backup`, but that is a
single slot overwritten on each deploy — two writes in a row and the original
is gone. This module keeps a rolling set of snapshots instead.

## How it works

`snapshot_flows()` is called immediately before each `post_flows()`. It does
its OWN `GET /flows` rather than accepting the caller's array, because most
write tools fetch the flows and then mutate that list in place — handing it
here would snapshot the NEW state under the name of the old one. Node-RED
still holds the previous state until the POST lands, so a fresh GET at this
moment is exactly the pre-write content.

## Fail closed

If the snapshot cannot be taken, the write is aborted. A backup that silently
fails is worse than no backup, because it is trusted.

## Restore

A snapshot is a complete, unmodified `/flows` array — the same shape
`replace_flows` accepts. To roll back:

    python -c "import json;print(json.dumps(json.load(open('<file>'))))"

then pass that array to `replace_flows`, or POST it straight to Node-RED:

    curl -u <user>:<pass> -X POST http://<nodered>/flows \\
         -H 'Content-Type: application/json' --data @<file>

Restoring is itself a destructive write, so it takes its own snapshot first —
a bad restore is recoverable too.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .errors import ErrorCode, create_error_response, raise_tool_error

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from .client import NodeRedClient

logger = logging.getLogger(__name__)

# Repo root: backup.py -> ha_mcp_nodered -> src -> <repo>. Derived from the
# module path rather than cwd because systemd's ReadWritePaths pins exactly
# this directory as the only durable writable location (ProtectHome=read-only,
# ProtectSystem=strict, and PrivateTmp wipes /tmp on restart).
_REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_BACKUP_DIR = _REPO_ROOT / "flow-backups"
DEFAULT_KEEP = 20


def backup_dir() -> Path:
    return Path(os.getenv("NODERED_BACKUP_DIR", str(DEFAULT_BACKUP_DIR)))


def backup_keep() -> int:
    raw = os.getenv("NODERED_BACKUP_KEEP", str(DEFAULT_KEEP))
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "NODERED_BACKUP_KEEP=%r is not an integer; using %d", raw, DEFAULT_KEEP
        )
        return DEFAULT_KEEP
    return max(1, value)


def _prune(directory: Path, keep: int) -> int:
    """Delete all but the newest `keep` snapshots. Never raises."""
    try:
        snapshots = sorted(
            directory.glob("flows-*.json"),
            key=lambda p: p.name,
            reverse=True,
        )
        removed = 0
        for stale in snapshots[keep:]:
            try:
                stale.unlink()
                removed += 1
            except OSError as exc:
                logger.warning("could not prune %s: %s", stale, exc)
        return removed
    except OSError as exc:
        # Pruning is housekeeping; never let it break a write that has a
        # good snapshot already on disk.
        logger.warning("prune failed in %s: %s", directory, exc)
        return 0


async def snapshot_flows(client: NodeRedClient, operation: str) -> Path:
    """Snapshot the CURRENT flows before a destructive write.

    Returns the path written. Aborts the caller via ToolError if the snapshot
    cannot be taken — see "Fail closed" above.
    """
    try:
        flows: list[dict[str, Any]] = await client.get_flows()
    except Exception as exc:
        logger.error("pre-write backup failed to read flows (%s): %s", operation, exc)
        raise_tool_error(
            create_error_response(
                ErrorCode.INTERNAL_ERROR,
                (
                    f"Aborted {operation}: could not read the current flows to "
                    f"back them up ({exc}). No change was made. Retry once "
                    "Node-RED is reachable."
                ),
            )
        )

    directory = backup_dir()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = directory / f"flows-{stamp}-{operation}.json"

    try:
        directory.mkdir(parents=True, exist_ok=True)
        # Write to a temp name and rename so a crash mid-write cannot leave a
        # truncated file that looks like a valid snapshot.
        partial = target.with_suffix(".json.partial")
        partial.write_text(json.dumps(flows, indent=2), encoding="utf-8")
        partial.replace(target)
    except OSError as exc:
        logger.error("pre-write backup failed to write %s: %s", target, exc)
        raise_tool_error(
            create_error_response(
                ErrorCode.INTERNAL_ERROR,
                (
                    f"Aborted {operation}: could not write the pre-write backup "
                    f"to {target} ({exc}). No change was made."
                ),
            )
        )

    _prune(directory, backup_keep())
    logger.info("pre-write backup for %s: %s (%d nodes)", operation, target, len(flows))
    return target
