"""Shared test fixtures.

Every write tool now takes a pre-write flow snapshot (see
`ha_mcp_nodered.backup`). Without redirection those snapshots land in the real
`flow-backups/` directory inside the repo whenever the suite runs, mixing test
fixture data into an operator's actual rollback history. The autouse fixture
below points the backup directory at a per-test tmp_path instead.
"""

import pytest


@pytest.fixture(autouse=True)
def isolate_flow_backups(tmp_path, monkeypatch):
    """Keep pre-write snapshots out of the repo during tests."""
    target = tmp_path / "flow-backups"
    monkeypatch.setenv("NODERED_BACKUP_DIR", str(target))
    return target
