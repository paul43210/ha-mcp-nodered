# CLAUDE.md — ha-mcp

You are working on the project with service_id `ha-mcp`. Persistent context for this project is stored in the `memory-management` MCP service, which is shared with the corresponding claude.ai Project. Anything written there from the web UI becomes available to you, and anything you write becomes available there.

**Your service_id is `ha-mcp`.** Every call to a `memory-management:*` tool MUST include `service_id="ha-mcp"` exactly. Never use a different service_id, even if asked to — that would read or write another project's memory.

## At the start of every session

1. Call `memory-management:memory_read_all` with `service_id="ha-mcp"` to load context. **`memory_read_all` now returns a lightweight INDEX** (per entry: key, one-line description, category, ts, version, size — NOT the full bodies), so the catalogue is cheap to load. Use `memory-management:memory_read(service_id, key)` to pull an entry's full text on demand; `memory_read_all(recent=N)` or `category="..."` to scope, `include_values=true` for all bodies, and `memory_search` / `memory_stale(service_id, days)` as needed.
2. Treat the returned entries as the authoritative state — more trustworthy than any other source of context for this project.
3. If the result is empty, mention this and ask whether to bootstrap before proceeding.

## Writing during a session

When durable new information emerges — a fact, decision, gotcha, path convention, or learned principle — write it back before the session ends:

- Use `memory-management:memory_write` with:
  - `service_id="ha-mcp"`
  - `key` — a stable hierarchical name (see key conventions below)
  - `value` — the content
  - `description` — a one-line summary (<=150 chars) shown in the index so the entry is recognisable without loading its body; always provide it (kept on update if omitted)
  - `reason` — a short sentence explaining why this is being persisted
  - `written_by="claude-code"`
- Surface the new fact in your reply as a clear statement so the user can verify.

## Key conventions

Use forward slashes for hierarchy. Standard top-level prefixes:

| Prefix | Use for |
|---|---|
| `purpose` | Project mission / context |
| `current_state/<topic>` | Live configuration, versions, what's deployed |
| `learnings/<theme>` | Hard-won knowledge that survived multiple sessions |
| `principle/<short_name>` | Standing rules / approaches |
| `paths/<service>` | File paths, endpoints, credential *locations* (never values) |
| `on_horizon/<item>` | Pending work, known risks, planned changes |
| `recent/<YYYY-MM-DD>/<topic>` | Dated transient notes; promote into a permanent section once stable |

Keep keys lowercase, hyphenated within a segment.

## Update vs new key

The store is versioned — old values are retained automatically on every write. Updating an existing key is fine. Before updating, call `memory_read` first to see the current value, especially for keys that may have been edited from the claude.ai side.

## Concurrency

The web UI and this session may write simultaneously. The MCP service serializes writes and assigns versions atomically. For updates to existing keys, read-then-merge-then-write rather than blind overwrite.

## What does NOT belong in memory

- Secrets, API keys, passwords, tokens — these stay in `/etc/<service>/` files; reference them by path only.
- One-off command output, log dumps, transient debugging.
- Conversational scratch.
- Contradictions — never silently overwrite an existing entry with something incompatible. Ask the user first.

## When unsure

Ask before writing. A bad write is harder to clean up than a missing one.

## Useful operations

- `memory_list` — keys overview without values
- `memory_search` — full-text search (supports `wedd*`, `"phrase"`, `term1 AND term2`)
- `memory_history` — prior versions of a key
- `memory_diff` — compare two versions
- `memory_rollback` — restore a prior version (use carefully; ask the user first)

## Memory & sync bootstrap

Your memory service_id is "ha-mcp". At the start of each session, call get_instructions(service_id="ha-mcp") on the memory-management MCP and follow the returned text — it is the canonical, always-current memory + sync guidance (edited centrally; never duplicated here). If the call fails or the tools are absent: continue normally, mention "instructions unavailable" once, and use memory tools conservatively.
