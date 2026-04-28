# ha-mcp-nodered

Standalone MCP server for the **Node-RED Admin API** — 11 tools for reading,
patching, and atomically deploying flows. Designed to be run alongside
[`homeassistant-ai/ha-mcp`](https://github.com/homeassistant-ai/ha-mcp)
(or anything else) — not as a fork or addition to it.

## Why a separate package

Upstream `ha-mcp` is for Home Assistant. Node-RED is a separate API with
a different auth model and a different write contract (fetch the whole
`/flows` array, mutate, post the whole thing back). Bundling Node-RED tools
into a HA-focused MCP added 11 tools to a project that's already over the
tool-count threshold where selection accuracy degrades. This split keeps each
server focused.

## Tools

| Category | Tool | Notes |
|---|---|---|
| Read | `list_flows` | Tabs + per-tab node counts |
| Read | `get_flow` | One tab and every node it contains |
| Read | `search_nodes` | Filter by exact `type` and/or case-insensitive name substring; optionally restrict to one flow |
| Read | `get_settings` | Node-RED runtime settings (version, palette categories, theme) |
| Trigger | `call_inject_node` | Fire an inject node by ID |
| Write | `update_node` | Patch one node's properties; cannot change `type` |
| Write | `update_flow_nodes` | Patch multiple nodes in one flow |
| Write | `replace_flow_nodes` | Replace every node inside one tab (other flows untouched) |
| Write | `create_flow` | Create a new flow tab with its initial nodes |
| Write | `delete_flow` | Delete a tab and every node inside it |
| Write | `replace_flows` | Replace the entire `/flows` array (full deployment) |

Each write tool does **GET → mutate → POST** atomically server-side, so the
agent never holds the full flows array in context.

## Install

```bash
uv sync --group dev   # development install (with tests)
uv sync --no-dev      # production install
```

## Configuration

Copy `.env.example` to `.env` and fill in:

```ini
NODERED_URL=https://your-ha-host/nodered-api
NODERED_USERNAME=your_user
NODERED_PASSWORD=your_password
```

Optional: `MCP_PORT`, `MCP_SECRET_PATH`, `LOG_LEVEL`, `NODERED_TIMEOUT`.

## Running

```bash
uv run ha-mcp-nodered        # stdio (Claude Desktop, MCP Inspector)
uv run ha-mcp-nodered-web    # HTTP transport on $MCP_PORT (default 8086)
```

For systemd / Apache deployment alongside an existing MCP server, see the
`build.sh` and `deploy.sh` scripts plus the systemd unit example below.

## Auth model

The HTTP transport uses a **secret URL path** (`MCP_SECRET_PATH`) — Apache
forwards a clean public URL to the local secret path. The token never appears
in the public URL.

## Migrating from the ha-mcp fork

If you were using the
[Node-RED tools fork](https://github.com/paul43210/ha-mcp/tree/feat/nodered-tools)
of `ha-mcp`, the tool names are different (no `ha_` or `nodered_` prefix —
the whole MCP is about Node-RED, so the prefix was redundant):

| Fork name | Standalone name |
|---|---|
| `ha_list_nodered_flows` | `list_flows` |
| `ha_get_nodered_flow` | `get_flow` |
| `ha_search_nodered_nodes` | `search_nodes` |
| `ha_get_nodered_settings` | `get_settings` |
| `ha_call_nodered_inject_node` | `call_inject_node` |
| `ha_update_nodered_node` | `update_node` |
| `ha_update_nodered_flow_nodes` | `update_flow_nodes` |
| `ha_replace_nodered_flow_nodes` | `replace_flow_nodes` |
| `ha_create_nodered_flow` | `create_flow` |
| `ha_delete_nodered_flow` | `delete_flow` |
| `ha_replace_nodered_flows` | `replace_flows` |

## License

MIT
