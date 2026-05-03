# OpenMemory Multi-User Setup

## Architecture

```
USERS (= persons, HARD isolation)
+- nolann (owner) +- personal
|                 +- nocode18
|                 +- zephly
|                 +- trading
|                 +- freelance
|                 +- shared       <-- readable by all Nolann agents (shared_default)
|
+- jess           +- personal
+- yoann          +- personal
+- matt           +- personal
+- djamila        +- personal

AGENTS = MCP clients, spawned at runtime (not pre-declared).
```

## MCP URL pattern

```
http://<host>:8765/mcp/{agent_id}/http/{user_id}
```

Examples:
- `http://localhost:8765/mcp/dev-zephly/http/nolann`
- `http://localhost:8765/mcp/jess-assistant/http/jess`

At the first request from a new `agent_id`, OpenMemory creates the
corresponding `App` row on-the-fly. Same for `user_id`.

## Memory routing

A memory's target zone (`app_id`) is determined by:

1. **Explicit prefix in text** (planned): `"[shared] my Twitter is @follox42"` -> routed to `shared`.
2. **Agent's own app** (default): if no prefix, the agent writes to its own zone.
3. **Promote/move later** (planned): MCP tools `promote_memory(id)` / `move_memory(id, target)`.

> Items 1 and 3 are tracked in MEM-4 ("Outils MCP routing").

## Default ACL

Apps with `shared_default: true` (e.g. `shared`) are readable by all agents of
the same user. Put your identity, social profiles, stack, generic preferences
there. Every agent of yours will see them naturally.

## Spawning a new agent

1. Pick an `agent_id` (e.g. `ops-nocode18`).
2. Add the MCP URL to your client (`~/.claude/settings.json`):
   ```json
   "ops-nocode18": {
     "type": "http",
     "url": "http://openmemory:8765/mcp/ops-nocode18/http/nolann"
   }
   ```
3. The first call creates the App with default ACL (access to `shared_default` apps).
4. Optional: restrict scope via REST API (planned MEM-4).

## Adding a user or app

1. Edit `config/users.yaml` or `config/apps.yaml`.
2. Restart the API container OR run inside the container: `python scripts/seed.py`.
3. The seed is **idempotent**: it only inserts what's missing.

## Stack

| Service          | Image                    | Role                                              |
|------------------|--------------------------|---------------------------------------------------|
| postgres         | postgres:16-alpine       | metadata (users, apps, ACL, history)              |
| qdrant           | qdrant/qdrant:v1.12.4    | vector store (semantic search)                    |
| neo4j            | neo4j:5.24-community     | graph memory (entities + relations); UI on :7474  |
| openmemory-mcp   | mem0/openmemory-mcp      | API + MCP server (port 8765)                      |
| openmemory-ui    | local build              | Next.js dashboard (port 3000)                     |

## Graph memory (Neo4j)

Enabled automatically when `NEO4J_URL` is set. The mem0 client builds an
entity-relationship graph alongside vector search. Inspect via Neo4j Browser
on `http://<host>:7474` (creds: `neo4j` / `${NEO4J_PASSWORD}`).

## Coolify deployment

- App: `openmemory` (uuid `osqkvaex8ppdnmms3qh7hlgy`)
- Repo: `follox42/mem0` branch `main` (PRs land via `dev`)
- Traefik handles HTTPS + routing (no Caddy needed)
- Tailscale-only ingress recommended for sensitive data

## Plane tracking

Project `MEM` (OpenMemory Stack):
- MEM-1 Backend multi-user dynamique
- MEM-2 Graph memory Neo4j
- MEM-3 Seed users + apps + ACL
- MEM-4 Outils MCP routing (prefixe + promote/move/tag)
- MEM-5 Notes KB Obsidian
