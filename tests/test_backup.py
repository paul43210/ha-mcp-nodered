"""Tests for the pre-write flow backup guard.

The point of this module is that a destructive write is never allowed to
proceed unbacked, so most of these tests assert on what does NOT happen.
"""

import json
from unittest.mock import AsyncMock

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from ha_mcp_nodered import backup
from ha_mcp_nodered.tools import register_tools


def _flows() -> list[dict]:
    return [
        {"id": "tab1", "type": "tab", "label": "Lights"},
        {"id": "n1", "type": "inject", "z": "tab1", "name": "Trigger", "wires": [[]]},
    ]


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.get_flows = AsyncMock(return_value=_flows())
    client.post_flows = AsyncMock(return_value="rev-1")
    return client


@pytest.fixture
def tools(mock_client):
    mcp: FastMCP = FastMCP(name="test")
    register_tools(mcp, mock_client)
    return mcp


async def _call(mcp: FastMCP, name: str, **kwargs):
    tool = await mcp.get_tool(name)
    return await tool.fn(**kwargs)


@pytest.mark.asyncio
async def test_snapshot_written_before_write(tools, mock_client, isolate_flow_backups):
    await _call(tools, "replace_flows", flows=[{"id": "new", "type": "tab"}])

    files = list(isolate_flow_backups.glob("flows-*-replace_flows.json"))
    assert len(files) == 1, "expected exactly one snapshot for the write"

    # The snapshot must hold the PRE-write flows, not what was just deployed.
    saved = json.loads(files[0].read_text())
    assert saved == _flows()


@pytest.mark.asyncio
async def test_snapshot_path_returned_to_caller(tools, isolate_flow_backups):
    result = await _call(tools, "replace_flows", flows=[])
    assert result["data"]["backup"].endswith("-replace_flows.json")


@pytest.mark.asyncio
async def test_write_aborted_when_flows_unreadable(tools, mock_client):
    """If the pre-write read fails, the write must not happen."""
    mock_client.get_flows = AsyncMock(side_effect=RuntimeError("node-red down"))

    with pytest.raises(ToolError):
        await _call(tools, "replace_flows", flows=[{"id": "x", "type": "tab"}])

    mock_client.post_flows.assert_not_called()


@pytest.mark.asyncio
async def test_write_aborted_when_snapshot_undwritable(
    tools, mock_client, monkeypatch, tmp_path
):
    """A backup directory that cannot be written aborts the write too."""
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("i am a file")
    monkeypatch.setenv("NODERED_BACKUP_DIR", str(blocker / "sub"))

    with pytest.raises(ToolError):
        await _call(tools, "replace_flows", flows=[{"id": "x", "type": "tab"}])

    mock_client.post_flows.assert_not_called()


@pytest.mark.asyncio
async def test_every_write_tool_snapshots(tools, isolate_flow_backups):
    """All six write paths must back up — not just replace_flows."""
    await _call(tools, "update_node", node_id="n1", patches={"name": "Renamed"})
    await _call(
        tools,
        "update_flow_nodes",
        flow_id="tab1",
        node_patches=[{"node_id": "n1", "patches": {"name": "B"}}],
    )
    await _call(tools, "replace_flow_nodes", flow_id="tab1", new_flow_nodes=[])
    await _call(
        tools,
        "create_flow",
        flow_tab={"id": "tabNew", "type": "tab", "label": "New"},
        flow_nodes=[],
    )
    await _call(tools, "delete_flow", flow_id="tab1")
    await _call(tools, "replace_flows", flows=[])

    operations = {
        p.name.rsplit("-", 1)[-1].removesuffix(".json")
        for p in isolate_flow_backups.glob("flows-*.json")
    }
    assert operations == {
        "update_node",
        "update_flow_nodes",
        "replace_flow_nodes",
        "create_flow",
        "delete_flow",
        "replace_flows",
    }


def test_retention_prunes_oldest(tmp_path, monkeypatch):
    monkeypatch.setenv("NODERED_BACKUP_DIR", str(tmp_path))
    monkeypatch.setenv("NODERED_BACKUP_KEEP", "3")
    for stamp in range(1, 6):
        (tmp_path / f"flows-2026080{stamp}T000000Z-replace_flows.json").write_text("[]")

    backup._prune(tmp_path, backup.backup_keep())

    remaining = sorted(p.name for p in tmp_path.glob("flows-*.json"))
    assert len(remaining) == 3
    assert remaining[0].startswith("flows-20260803")  # oldest two pruned


def test_keep_falls_back_on_garbage(monkeypatch):
    monkeypatch.setenv("NODERED_BACKUP_KEEP", "not-a-number")
    assert backup.backup_keep() == backup.DEFAULT_KEEP
