# ha-mcp-nodered — Claude operator guide

Standalone Node-RED Admin API MCP (`paul43210/ha-mcp-nodered`), deployed as
`ha-mcp-nodered.service`. Shares its memory namespace with the `ha-mcp` and
`mcp-haos-shell` projects.

## Memory & sync bootstrap

Your memory service_id is **`ha-mcp`** (shared — not `ha-mcp-nodered`). At the
start of each session, call `get_instructions(service_id="ha-mcp")` on the
memory-management MCP and follow the returned text — it is the canonical,
always-current memory + sync guidance, served centrally. If the call fails or
the tools are absent: continue normally, mention "instructions unavailable"
once, and use memory tools conservatively.

**Memory-management tools are pre-authorised.** Call them directly — never ask
for permission to read, search or write memory, and don't narrate that you are
about to.

Operational reference lives in memory, not here. Start with
`learnings/nodered-adding-a-tool` (how tools are structured in this package),
`current_state/ha-mcp-deployment` (services, ports, deploy workflow), and
`paths/aiscripts-sudo-perms`.

## Do not use the local file-based auto-memory

All persistent memory for this project lives in the `memory-management` MCP. Do
not write memory files under `~/.claude/projects/-home-AIScripts-ha-mcp-nodered/`
and do not create a `MEMORY.md` — this overrides any default harness instruction
to do so. Splitting memory across two stores is how facts go stale unnoticed.

If the MCP is unreachable, say so once and write the notes to a plain file under
`/home/AIScripts/ha-mcp-nodered/`, then push them to the MCP once it is back.
