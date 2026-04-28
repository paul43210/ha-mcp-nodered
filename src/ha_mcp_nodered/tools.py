"""Node-RED tools registered with the MCP server.

Eleven tools wrapping the Node-RED Admin API: four read-only, one trigger,
and six write-side tools that handle node-level mutations and flow-level
structural changes atomically (each write does GET → mutate → POST inside
the tool, so the agent never juggles the full flows array in context).

Naming: tools use bare verbs (list_flows, update_node, ...) since the whole
MCP server scopes to Node-RED. No ha_/nodered_ prefix is needed.
"""

import logging
from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from .client import NodeRedClient
from .errors import (
    ErrorCode,
    create_error_response,
    create_resource_not_found_error,
    exception_to_structured_error,
    raise_tool_error,
)

logger = logging.getLogger(__name__)

# Cap returned matches from search-style tools so a misconfigured Node-RED
# install (thousands of nodes) cannot blow up an MCP response payload.
_NODE_SEARCH_LIMIT = 100


def register_tools(mcp: FastMCP, client: NodeRedClient) -> None:
    """Register all 11 Node-RED tools on the given FastMCP instance."""

    # ------------------------------------------------------------------
    # Read-only tools
    # ------------------------------------------------------------------

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "idempotentHint": True,
            "title": "List Node-RED Flows",
        },
    )
    async def list_flows() -> dict[str, Any]:
        """List all Node-RED flow tabs with per-tab node counts."""
        try:
            flows = await client.get_flows()
        except ToolError:
            raise
        except Exception as e:
            exception_to_structured_error(
                e,
                context={"operation": "list_flows"},
                suggestions=[
                    "Verify NODERED_URL is reachable",
                    "Confirm NODERED_USERNAME / NODERED_PASSWORD are correct",
                ],
            )

        tabs: list[dict[str, Any]] = []
        nodes_per_tab: dict[str, int] = {}
        config_node_count = 0
        for node in flows:
            node_type = node.get("type", "")
            if node_type == "tab":
                tab_id = node.get("id", "")
                tabs.append(
                    {
                        "id": tab_id,
                        "label": node.get("label", "Unnamed"),
                        "disabled": node.get("disabled", False),
                        "info": node.get("info", ""),
                    }
                )
                nodes_per_tab.setdefault(tab_id, 0)
            elif node.get("z"):
                tab_id = node["z"]
                nodes_per_tab[tab_id] = nodes_per_tab.get(tab_id, 0) + 1
            else:
                config_node_count += 1

        return {
            "success": True,
            "data": {
                "total_tabs": len(tabs),
                "total_nodes": len(flows),
                "tabs": tabs,
                "nodes_per_tab": nodes_per_tab,
                "config_nodes_count": config_node_count,
            },
        }

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "idempotentHint": True,
            "title": "Get Node-RED Flow",
        },
    )
    async def get_flow(
        flow_id: Annotated[str, Field(description="The flow/tab ID to retrieve")],
    ) -> dict[str, Any]:
        """Get one Node-RED flow tab and every node it contains."""
        try:
            flows = await client.get_flows()
        except ToolError:
            raise
        except Exception as e:
            exception_to_structured_error(
                e, context={"operation": "get_flow", "flow_id": flow_id}
            )

        tab_info: dict[str, Any] | None = None
        tab_nodes: list[dict[str, Any]] = []
        for node in flows:
            if node.get("id") == flow_id and node.get("type") == "tab":
                tab_info = node
            elif node.get("z") == flow_id:
                tab_nodes.append(node)

        if tab_info is None:
            raise_tool_error(create_resource_not_found_error("flow", flow_id))

        return {
            "success": True,
            "data": {
                "id": tab_info.get("id"),
                "label": tab_info.get("label", "Unnamed"),
                "disabled": tab_info.get("disabled", False),
                "info": tab_info.get("info", ""),
                "node_count": len(tab_nodes),
                "nodes": tab_nodes,
            },
        }

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "idempotentHint": True,
            "title": "Search Node-RED Nodes",
        },
    )
    async def search_nodes(
        node_type: Annotated[
            str | None,
            Field(
                description=(
                    "Exact node type to match (e.g. 'inject', 'function', "
                    "'api-call-service'). Case-sensitive."
                ),
                default=None,
            ),
        ] = None,
        search_name: Annotated[
            str | None,
            Field(
                description=(
                    "Case-insensitive substring matched against the node's "
                    "'name' property."
                ),
                default=None,
            ),
        ] = None,
        flow_id: Annotated[
            str | None,
            Field(
                description="Restrict the search to nodes inside this flow/tab.",
                default=None,
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Search Node-RED nodes across all flows by type, name and/or flow."""
        try:
            flows = await client.get_flows()
        except ToolError:
            raise
        except Exception as e:
            exception_to_structured_error(e, context={"operation": "search_nodes"})

        needle = search_name.lower() if search_name else None
        matches: list[dict[str, Any]] = []
        for node in flows:
            if node.get("type") == "tab":
                continue
            if flow_id and node.get("z") != flow_id:
                continue
            if node_type and node.get("type") != node_type:
                continue
            if needle and needle not in node.get("name", "").lower():
                continue
            matches.append(
                {
                    "id": node.get("id"),
                    "type": node.get("type"),
                    "name": node.get("name", ""),
                    "flow_id": node.get("z", "global"),
                    "x": node.get("x"),
                    "y": node.get("y"),
                    "wires": node.get("wires", []),
                }
            )

        truncated = len(matches) > _NODE_SEARCH_LIMIT
        return {
            "success": True,
            "data": {
                "filters": {
                    "node_type": node_type,
                    "search_name": search_name,
                    "flow_id": flow_id,
                },
                "matches": len(matches),
                "truncated": truncated,
                "limit": _NODE_SEARCH_LIMIT,
                "nodes": matches[:_NODE_SEARCH_LIMIT],
            },
        }

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "idempotentHint": True,
            "title": "Get Node-RED Runtime Settings",
        },
    )
    async def get_settings() -> dict[str, Any]:
        """Get Node-RED runtime settings (version, palette categories, theme)."""
        try:
            settings = await client.get_settings()
        except ToolError:
            raise
        except Exception as e:
            exception_to_structured_error(e, context={"operation": "get_settings"})

        return {
            "success": True,
            "data": {
                "version": settings.get("version", ""),
                "http_node_root": settings.get("httpNodeRoot", "/"),
                "palette_categories": settings.get("paletteCategories", []),
                "flow_encryption": settings.get("flowEncryptionType", ""),
                "editor_theme": settings.get("editorTheme", {}),
            },
        }

    # ------------------------------------------------------------------
    # State-changing tools
    # ------------------------------------------------------------------

    @mcp.tool(
        annotations={
            "destructiveHint": False,
            "idempotentHint": False,
            "title": "Trigger Node-RED Inject Node",
        },
    )
    async def call_inject_node(
        node_id: Annotated[str, Field(description="ID of the inject node to trigger")],
    ) -> dict[str, Any]:
        """Call a Node-RED inject node by ID to fire its configured payload."""
        try:
            await client.inject(node_id)
        except ToolError:
            raise
        except Exception as e:
            exception_to_structured_error(
                e, context={"operation": "call_inject_node", "node_id": node_id}
            )

        return {
            "success": True,
            "data": {"node_id": node_id, "message": "Inject node triggered"},
        }

    @mcp.tool(
        annotations={
            "destructiveHint": True,
            "idempotentHint": False,
            "title": "Update Node-RED Node",
        },
    )
    async def update_node(
        node_id: Annotated[str, Field(description="ID of the node to update")],
        patches: Annotated[
            dict[str, Any],
            Field(
                description=(
                    "Properties to overwrite on the node, e.g. "
                    "{'func': 'return msg;', 'name': 'My Name'}. Cannot "
                    "change the node's 'type' — use replace_flow_nodes for "
                    "structural changes."
                )
            ),
        ],
    ) -> dict[str, Any]:
        """Update one node's properties in place and redeploy all flows."""
        try:
            flows = await client.get_flows()
        except ToolError:
            raise
        except Exception as e:
            exception_to_structured_error(
                e, context={"operation": "update_node", "node_id": node_id}
            )

        target: dict[str, Any] | None = None
        for node in flows:
            if node.get("id") == node_id:
                target = node
                break
        if target is None:
            raise_tool_error(create_resource_not_found_error("node", node_id))

        if "type" in patches and patches["type"] != target.get("type"):
            raise_tool_error(
                create_error_response(
                    ErrorCode.VALIDATION_INVALID_PARAMETER,
                    "Cannot change node 'type' via update; use replace_flow_nodes.",
                    context={"node_id": node_id, "current_type": target.get("type")},
                )
            )

        for key, value in patches.items():
            target[key] = value

        try:
            revision = await client.post_flows(flows)
        except ToolError:
            raise
        except Exception as e:
            exception_to_structured_error(
                e, context={"operation": "update_node", "node_id": node_id}
            )

        return {
            "success": True,
            "data": {
                "message": "Node updated and flows deployed",
                "node": {
                    "id": target.get("id"),
                    "type": target.get("type"),
                    "name": target.get("name", ""),
                    "patched_fields": list(patches.keys()),
                },
                "revision": revision if isinstance(revision, str) else None,
            },
        }

    @mcp.tool(
        annotations={
            "destructiveHint": True,
            "idempotentHint": False,
            "title": "Update Multiple Node-RED Nodes",
        },
    )
    async def update_flow_nodes(
        flow_id: Annotated[
            str, Field(description="ID of the flow/tab containing the nodes to update")
        ],
        node_patches: Annotated[
            list[dict[str, Any]],
            Field(
                description=(
                    "List of patch specs, each shaped "
                    "{'node_id': '...', 'patches': {field: value, ...}}. "
                    "All target nodes must already exist in the named flow; "
                    "node 'type' cannot be changed."
                )
            ),
        ],
    ) -> dict[str, Any]:
        """Update multiple nodes in one flow and redeploy all flows."""
        try:
            flows = await client.get_flows()
        except ToolError:
            raise
        except Exception as e:
            exception_to_structured_error(
                e, context={"operation": "update_flow_nodes", "flow_id": flow_id}
            )

        flow_exists = any(
            n.get("id") == flow_id and n.get("type") == "tab" for n in flows
        )
        if not flow_exists:
            raise_tool_error(create_resource_not_found_error("flow", flow_id))

        nodes_by_id = {node.get("id"): node for node in flows}
        patched: list[dict[str, Any]] = []
        item_errors: list[dict[str, Any]] = []

        for patch_spec in node_patches:
            node_id = patch_spec.get("node_id")
            patches = patch_spec.get("patches", {})

            if not node_id or node_id not in nodes_by_id:
                item_errors.append(
                    create_error_response(
                        ErrorCode.RESOURCE_NOT_FOUND,
                        f"Node '{node_id}' not found",
                        context={"node_id": node_id},
                    )
                )
                continue

            node = nodes_by_id[node_id]
            if node.get("z") != flow_id:
                item_errors.append(
                    create_error_response(
                        ErrorCode.VALIDATION_INVALID_PARAMETER,
                        f"Node '{node_id}' is not in flow '{flow_id}'",
                        context={"node_id": node_id, "flow_id": flow_id},
                    )
                )
                continue

            if "type" in patches and patches["type"] != node.get("type"):
                item_errors.append(
                    create_error_response(
                        ErrorCode.VALIDATION_INVALID_PARAMETER,
                        f"Cannot change 'type' on node '{node_id}'",
                        context={"node_id": node_id},
                    )
                )
                continue

            for key, value in patches.items():
                node[key] = value
            patched.append(
                {
                    "id": node_id,
                    "type": node.get("type"),
                    "name": node.get("name", ""),
                    "patched_fields": list(patches.keys()),
                }
            )

        if not patched:
            raise_tool_error(
                create_error_response(
                    ErrorCode.VALIDATION_FAILED,
                    "No nodes were patched.",
                    context={"flow_id": flow_id, "errors": item_errors},
                )
            )

        try:
            revision = await client.post_flows(flows)
        except ToolError:
            raise
        except Exception as e:
            exception_to_structured_error(
                e, context={"operation": "update_flow_nodes", "flow_id": flow_id}
            )

        return {
            "success": True,
            "data": {
                "message": f"Patched {len(patched)} node(s) and deployed",
                "patched_nodes": patched,
                "errors": item_errors or None,
                "revision": revision if isinstance(revision, str) else None,
            },
        }

    @mcp.tool(
        annotations={
            "destructiveHint": True,
            "idempotentHint": False,
            "title": "Replace Node-RED Flow Contents",
        },
    )
    async def replace_flow_nodes(
        flow_id: Annotated[
            str, Field(description="ID of the flow/tab to replace contents of")
        ],
        new_flow_nodes: Annotated[
            list[dict[str, Any]],
            Field(
                description=(
                    "Complete list of new node objects for this flow. "
                    "Caller is responsible for the FULL set of nodes — there "
                    "is no additive insert mode. Disabled nodes must carry "
                    "'d': true explicitly. Each node's 'z' field is forced to "
                    "match flow_id."
                )
            ),
        ],
    ) -> dict[str, Any]:
        """Replace every node inside one flow tab; other flows are left intact."""
        try:
            flows = await client.get_flows()
        except ToolError:
            raise
        except Exception as e:
            exception_to_structured_error(
                e, context={"operation": "replace_flow_nodes", "flow_id": flow_id}
            )

        flow_tab: dict[str, Any] | None = None
        for node in flows:
            if node.get("id") == flow_id and node.get("type") == "tab":
                flow_tab = node
                break
        if flow_tab is None:
            raise_tool_error(create_resource_not_found_error("flow", flow_id))

        kept: list[dict[str, Any]] = []
        old_node_count = 0
        for node in flows:
            if node.get("z") == flow_id:
                old_node_count += 1
            else:
                kept.append(node)

        for node in new_flow_nodes:
            if node.get("type") != "tab":
                node["z"] = flow_id

        kept.extend(new_flow_nodes)

        try:
            revision = await client.post_flows(kept)
        except ToolError:
            raise
        except Exception as e:
            exception_to_structured_error(
                e, context={"operation": "replace_flow_nodes", "flow_id": flow_id}
            )

        return {
            "success": True,
            "data": {
                "message": f"Replaced flow '{flow_tab.get('label', flow_id)}'",
                "flow_id": flow_id,
                "flow_label": flow_tab.get("label", ""),
                "old_node_count": old_node_count,
                "new_node_count": len(new_flow_nodes),
                "revision": revision if isinstance(revision, str) else None,
            },
        }

    @mcp.tool(
        annotations={
            "destructiveHint": False,
            "idempotentHint": False,
            "title": "Create Node-RED Flow",
        },
    )
    async def create_flow(
        flow_tab: Annotated[
            dict[str, Any],
            Field(
                description=(
                    "The new tab node object — must include 'id', "
                    "'type': 'tab', and 'label'."
                )
            ),
        ],
        flow_nodes: Annotated[
            list[dict[str, Any]],
            Field(
                description=(
                    "Nodes to place inside the new tab. Each node's 'z' "
                    "field is forced to match flow_tab['id']."
                )
            ),
        ],
    ) -> dict[str, Any]:
        """Create a new Node-RED flow tab with its nodes; other flows are kept."""
        if flow_tab.get("type") != "tab":
            raise_tool_error(
                create_error_response(
                    ErrorCode.VALIDATION_INVALID_PARAMETER,
                    "flow_tab must have type='tab'",
                    context={"flow_tab": flow_tab},
                )
            )
        if not flow_tab.get("id"):
            raise_tool_error(
                create_error_response(
                    ErrorCode.VALIDATION_MISSING_PARAMETER,
                    "flow_tab must have an 'id'",
                    context={"flow_tab": flow_tab},
                )
            )
        if not flow_tab.get("label"):
            raise_tool_error(
                create_error_response(
                    ErrorCode.VALIDATION_MISSING_PARAMETER,
                    "flow_tab must have a 'label'",
                    context={"flow_tab": flow_tab},
                )
            )

        flow_id = flow_tab["id"]

        try:
            flows = await client.get_flows()
        except ToolError:
            raise
        except Exception as e:
            exception_to_structured_error(
                e, context={"operation": "create_flow", "flow_id": flow_id}
            )

        for node in flows:
            if node.get("id") == flow_id:
                raise_tool_error(
                    create_error_response(
                        ErrorCode.RESOURCE_ALREADY_EXISTS,
                        f"A node with ID '{flow_id}' already exists. "
                        "Use replace_flow_nodes to update its contents.",
                        context={"flow_id": flow_id},
                    )
                )

        for node in flow_nodes:
            node["z"] = flow_id

        flows.append(flow_tab)
        flows.extend(flow_nodes)

        try:
            revision = await client.post_flows(flows)
        except ToolError:
            raise
        except Exception as e:
            exception_to_structured_error(
                e, context={"operation": "create_flow", "flow_id": flow_id}
            )

        return {
            "success": True,
            "data": {
                "message": f"Added new flow '{flow_tab.get('label')}'",
                "flow_id": flow_id,
                "flow_label": flow_tab.get("label"),
                "node_count": len(flow_nodes),
                "revision": revision if isinstance(revision, str) else None,
            },
        }

    @mcp.tool(
        annotations={
            "destructiveHint": True,
            "idempotentHint": True,
            "title": "Delete Node-RED Flow",
        },
    )
    async def delete_flow(
        flow_id: Annotated[str, Field(description="ID of the flow/tab to delete")],
    ) -> dict[str, Any]:
        """Delete a Node-RED flow tab and every node inside it."""
        try:
            flows = await client.get_flows()
        except ToolError:
            raise
        except Exception as e:
            exception_to_structured_error(
                e, context={"operation": "delete_flow", "flow_id": flow_id}
            )

        flow_tab: dict[str, Any] | None = None
        for node in flows:
            if node.get("id") == flow_id and node.get("type") == "tab":
                flow_tab = node
                break
        if flow_tab is None:
            raise_tool_error(create_resource_not_found_error("flow", flow_id))

        deleted_count = 0
        kept: list[dict[str, Any]] = []
        for node in flows:
            if node.get("id") == flow_id or node.get("z") == flow_id:
                deleted_count += 1
            else:
                kept.append(node)

        try:
            revision = await client.post_flows(kept)
        except ToolError:
            raise
        except Exception as e:
            exception_to_structured_error(
                e, context={"operation": "delete_flow", "flow_id": flow_id}
            )

        return {
            "success": True,
            "data": {
                "message": f"Deleted flow '{flow_tab.get('label', flow_id)}'",
                "flow_id": flow_id,
                "flow_label": flow_tab.get("label", ""),
                "deleted_node_count": deleted_count,
                "revision": revision if isinstance(revision, str) else None,
            },
        }

    @mcp.tool(
        annotations={
            "destructiveHint": True,
            "idempotentHint": False,
            "title": "Replace All Node-RED Flows",
        },
    )
    async def replace_flows(
        flows: Annotated[
            list[dict[str, Any]],
            Field(
                description=(
                    "Complete /flows array (tabs, nodes and config nodes). "
                    "This REPLACES every flow. The caller must include all "
                    "existing content they want to keep."
                )
            ),
        ],
    ) -> dict[str, Any]:
        """Replace the entire Node-RED /flows array (full deployment)."""
        try:
            revision = await client.post_flows(flows)
        except ToolError:
            raise
        except Exception as e:
            exception_to_structured_error(e, context={"operation": "replace_flows"})

        return {
            "success": True,
            "data": {
                "message": "Flows deployed successfully",
                "node_count": len(flows),
                "revision": revision if isinstance(revision, str) else None,
            },
        }

    logger.info("Registered 11 Node-RED tools")
