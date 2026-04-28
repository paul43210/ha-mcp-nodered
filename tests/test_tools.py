"""Unit tests for the 11 Node-RED tools, exercising them against a mocked NodeRedClient."""

import json
from unittest.mock import AsyncMock

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from ha_mcp_nodered.tools import register_tools


def _flows_fixture() -> list[dict]:
    return [
        {"id": "tab1", "type": "tab", "label": "Lights", "disabled": False},
        {"id": "tab2", "type": "tab", "label": "Bathroom", "disabled": False},
        {
            "id": "n1",
            "type": "inject",
            "z": "tab1",
            "name": "Morning Trigger",
            "x": 100,
            "y": 100,
            "wires": [["n2"]],
        },
        {
            "id": "n2",
            "type": "function",
            "z": "tab1",
            "name": "Compute Brightness",
            "x": 250,
            "y": 100,
            "wires": [[]],
            "func": "return msg;",
        },
        {
            "id": "n3",
            "type": "api-call-service",
            "z": "tab2",
            "name": "Turn on Fan",
            "x": 100,
            "y": 200,
            "wires": [[]],
        },
        {"id": "cfg1", "type": "server", "name": "HA Server"},
    ]


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.get_flows = AsyncMock(return_value=_flows_fixture())
    client.post_flows = AsyncMock(return_value="rev-abc-123")
    client.get_settings = AsyncMock(
        return_value={
            "version": "4.0.2",
            "httpNodeRoot": "/",
            "paletteCategories": ["common", "function"],
            "flowEncryptionType": "user",
            "editorTheme": {"projects": {"enabled": False}},
        }
    )
    client.inject = AsyncMock(return_value="OK")
    return client


@pytest.fixture
def registered_tools(mock_client):
    """Register tools against a fresh FastMCP and return a name → callable map.

    We use FastMCP's get_tool() to fetch each registered tool, then unwrap the
    decorator chain to get back the bare async function so we can invoke it
    directly without going through the MCP request lifecycle.
    """
    mcp: FastMCP = FastMCP(name="test")
    register_tools(mcp, mock_client)
    return mcp


async def _call(mcp: FastMCP, name: str, **kwargs):
    """Invoke a registered tool by name, returning its raw result dict."""
    tool = await mcp.get_tool(name)
    fn = tool.fn
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return await fn(**kwargs)


def _parse_tool_error(exc):
    return json.loads(str(exc.value))


# ---------------------------------------------------------------------------
# Read-only tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_flows_summarises_tabs_and_nodes(registered_tools):
    result = await _call(registered_tools, "list_flows")
    data = result["data"]
    assert data["total_tabs"] == 2
    assert data["total_nodes"] == 6
    assert data["nodes_per_tab"] == {"tab1": 2, "tab2": 1}
    assert data["config_nodes_count"] == 1


@pytest.mark.asyncio
async def test_get_flow_returns_tab_with_nodes(registered_tools):
    result = await _call(registered_tools, "get_flow", flow_id="tab1")
    data = result["data"]
    assert data["label"] == "Lights"
    assert data["node_count"] == 2
    assert {n["id"] for n in data["nodes"]} == {"n1", "n2"}


@pytest.mark.asyncio
async def test_get_flow_unknown_id_raises(registered_tools):
    with pytest.raises(ToolError) as exc:
        await _call(registered_tools, "get_flow", flow_id="missing")
    assert _parse_tool_error(exc)["error"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_search_nodes_filters_by_type_and_substring(registered_tools):
    result = await _call(
        registered_tools, "search_nodes", node_type="function", search_name="brightness"
    )
    assert result["data"]["matches"] == 1
    assert result["data"]["nodes"][0]["id"] == "n2"


@pytest.mark.asyncio
async def test_search_nodes_is_case_insensitive(registered_tools):
    result = await _call(registered_tools, "search_nodes", search_name="MORNING")
    ids = {n["id"] for n in result["data"]["nodes"]}
    assert "n1" in ids


@pytest.mark.asyncio
async def test_get_settings_passes_through(registered_tools):
    result = await _call(registered_tools, "get_settings")
    assert result["data"]["version"] == "4.0.2"


# ---------------------------------------------------------------------------
# Trigger / write tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_inject_node(registered_tools, mock_client):
    result = await _call(registered_tools, "call_inject_node", node_id="n1")
    mock_client.inject.assert_awaited_once_with("n1")
    assert result["data"]["node_id"] == "n1"


@pytest.mark.asyncio
async def test_update_node_writes_back(registered_tools, mock_client):
    result = await _call(
        registered_tools,
        "update_node",
        node_id="n2",
        patches={"name": "Renamed", "func": "return null;"},
    )
    deployed = mock_client.post_flows.await_args.args[0]
    n2 = next(n for n in deployed if n["id"] == "n2")
    assert n2["name"] == "Renamed"
    assert n2["func"] == "return null;"
    assert set(result["data"]["node"]["patched_fields"]) == {"name", "func"}


@pytest.mark.asyncio
async def test_update_node_missing_raises(registered_tools, mock_client):
    with pytest.raises(ToolError) as exc:
        await _call(
            registered_tools, "update_node", node_id="ghost", patches={"name": "X"}
        )
    assert _parse_tool_error(exc)["error"]["code"] == "RESOURCE_NOT_FOUND"
    mock_client.post_flows.assert_not_called()


@pytest.mark.asyncio
async def test_update_node_rejects_type_change(registered_tools, mock_client):
    with pytest.raises(ToolError) as exc:
        await _call(
            registered_tools, "update_node", node_id="n1", patches={"type": "function"}
        )
    assert _parse_tool_error(exc)["error"]["code"] == "VALIDATION_INVALID_PARAMETER"
    mock_client.post_flows.assert_not_called()


@pytest.mark.asyncio
async def test_update_flow_nodes_applies_multiple(registered_tools, mock_client):
    result = await _call(
        registered_tools,
        "update_flow_nodes",
        flow_id="tab1",
        node_patches=[
            {"node_id": "n1", "patches": {"name": "T2"}},
            {"node_id": "n2", "patches": {"func": "return 42;"}},
        ],
    )
    assert result["data"]["message"].startswith("Patched 2")
    deployed = mock_client.post_flows.await_args.args[0]
    by_id = {n["id"]: n for n in deployed}
    assert by_id["n1"]["name"] == "T2"
    assert by_id["n2"]["func"] == "return 42;"


@pytest.mark.asyncio
async def test_update_flow_nodes_collects_wrong_flow_errors(
    registered_tools, mock_client
):
    result = await _call(
        registered_tools,
        "update_flow_nodes",
        flow_id="tab1",
        node_patches=[
            {"node_id": "n1", "patches": {"name": "ok"}},
            {"node_id": "n3", "patches": {"name": "wrong tab"}},
        ],
    )
    assert len(result["data"]["patched_nodes"]) == 1
    assert result["data"]["errors"] is not None


@pytest.mark.asyncio
async def test_replace_flow_nodes_swaps_and_forces_z(registered_tools, mock_client):
    new_nodes = [
        {"id": "new1", "type": "inject", "name": "New Inject", "wires": []},
        {"id": "new2", "type": "debug", "name": "Dbg", "wires": []},
    ]
    result = await _call(
        registered_tools,
        "replace_flow_nodes",
        flow_id="tab1",
        new_flow_nodes=new_nodes,
    )
    assert result["data"]["old_node_count"] == 2
    deployed = mock_client.post_flows.await_args.args[0]
    deployed_ids = {n["id"] for n in deployed}
    assert {"n1", "n2"}.isdisjoint(deployed_ids)
    assert {"new1", "new2", "tab1", "tab2", "n3", "cfg1"} <= deployed_ids
    for node in deployed:
        if node["id"] in {"new1", "new2"}:
            assert node["z"] == "tab1"


@pytest.mark.asyncio
async def test_create_flow_appends(registered_tools, mock_client):
    new_tab = {"id": "tab3", "type": "tab", "label": "Garage"}
    new_nodes = [{"id": "g1", "type": "inject", "name": "GT", "wires": []}]
    result = await _call(
        registered_tools, "create_flow", flow_tab=new_tab, flow_nodes=new_nodes
    )
    assert result["data"]["flow_id"] == "tab3"
    deployed_by_id = {n["id"]: n for n in mock_client.post_flows.await_args.args[0]}
    assert deployed_by_id["tab3"]["type"] == "tab"
    assert deployed_by_id["g1"]["z"] == "tab3"


@pytest.mark.asyncio
async def test_create_flow_rejects_duplicate_id(registered_tools, mock_client):
    with pytest.raises(ToolError) as exc:
        await _call(
            registered_tools,
            "create_flow",
            flow_tab={"id": "tab1", "type": "tab", "label": "dup"},
            flow_nodes=[],
        )
    assert _parse_tool_error(exc)["error"]["code"] == "RESOURCE_ALREADY_EXISTS"
    mock_client.post_flows.assert_not_called()


@pytest.mark.asyncio
async def test_delete_flow_removes_tab_and_children(registered_tools, mock_client):
    result = await _call(registered_tools, "delete_flow", flow_id="tab1")
    assert result["data"]["deleted_node_count"] == 3  # tab + n1 + n2
    deployed_ids = {n["id"] for n in mock_client.post_flows.await_args.args[0]}
    assert "tab1" not in deployed_ids
    assert "n1" not in deployed_ids


@pytest.mark.asyncio
async def test_replace_flows_passes_through(registered_tools, mock_client):
    payload = [{"id": "tabX", "type": "tab", "label": "Replacement"}]
    result = await _call(registered_tools, "replace_flows", flows=payload)
    mock_client.post_flows.assert_awaited_once_with(payload)
    assert result["data"]["node_count"] == 1


# ---------------------------------------------------------------------------
# Error mapping (sanity checks for exception_to_structured_error)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connection_error_maps_to_connection_failed(
    registered_tools, mock_client
):
    from ha_mcp_nodered.client import NodeRedConnectionError

    mock_client.get_flows.side_effect = NodeRedConnectionError("connection refused")
    with pytest.raises(ToolError) as exc:
        await _call(registered_tools, "list_flows")
    code = _parse_tool_error(exc)["error"]["code"]
    assert code == "CONNECTION_FAILED"


@pytest.mark.asyncio
async def test_auth_error_maps_to_auth_invalid_token(registered_tools, mock_client):
    from ha_mcp_nodered.client import NodeRedAuthError

    mock_client.get_flows.side_effect = NodeRedAuthError("auth failed")
    with pytest.raises(ToolError) as exc:
        await _call(registered_tools, "list_flows")
    code = _parse_tool_error(exc)["error"]["code"]
    assert code == "AUTH_INVALID_TOKEN"
