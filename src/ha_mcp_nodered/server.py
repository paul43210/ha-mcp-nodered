"""FastMCP server setup for ha-mcp-nodered."""

import logging

from fastmcp import FastMCP

from . import __version__
from .client import NodeRedClient
from .config import Settings, get_settings
from .tools import register_tools

logger = logging.getLogger(__name__)

_INSTRUCTIONS = """\
This MCP server exposes the Node-RED Admin API as 11 tools for reading,
patching, and deploying flows.

READ:
- list_flows / get_flow / search_nodes / get_settings

TRIGGER:
- call_inject_node

WRITE (each does GET → mutate → POST atomically — no agent-side state):
- update_node / update_flow_nodes
- replace_flow_nodes  (replace all nodes inside one tab)
- create_flow / delete_flow
- replace_flows  (replace the entire /flows array — full deployment)

Behavioural notes:
- update_node and update_flow_nodes only mutate existing properties; they
  cannot change a node's 'type'. Use replace_flow_nodes for structural changes.
- replace_flow_nodes expects the FULL new node list for the tab. There is
  no additive insert mode. Disabled nodes must carry "d": true explicitly.
- search_nodes filters by 'name' (case-insensitive substring) and/or 'type'
  (exact match), optionally restricted to one flow.
"""


def build_server(client: NodeRedClient | None = None) -> FastMCP:
    """Create a FastMCP server, register the Node-RED tools, return it.

    A custom client can be injected for tests; otherwise one is built from
    the active Settings.
    """
    settings: Settings = get_settings()
    nodered_client = client or NodeRedClient(
        base_url=settings.nodered_url,
        username=settings.nodered_username,
        password=settings.nodered_password,
        timeout=settings.timeout,
    )

    mcp: FastMCP = FastMCP(
        name=settings.mcp_server_name,
        version=__version__,
        instructions=_INSTRUCTIONS,
    )
    register_tools(mcp, nodered_client)
    logger.info("ha-mcp-nodered %s ready", __version__)
    return mcp
