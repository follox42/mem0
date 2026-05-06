# OpenMemory Multi-User Setup

> Pour le modele complet d'organisation (5 niveaux : user / app / categories / tags / graph) -> voir [TAXONOMY.md](TAXONOMY.md).

## Architecture

```
USERS (= persons, HARD isolation)
+-- nolann (owner)
|     +-- perso        (vie privee)
|     +-- business     (entreprises + sales)
|     +-- tools        (infra technique perso)
|     +-- learn        (shared_default - transverse)
|     +-- shared       (shared_default - identite)
|     +-- inbox        (capture brute, a trier)
|
+-- jess           +-- personal
+-- yoann          +-- personal
+-- matt           +-- personal
+-- djamila        +-- personal

AGENTS = MCP clients, spawned at runtime (not pre-declared).
CATEGORIES = 31 entries dans config/categories.yaml, auto-classifiees.
```

## Modele 5-niveaux (resume)

| # | Niveau | Cardinalite | Modifiable | Exemple |
|---|---|---|---|---|
| 1 | `user_id` | 5 (HARD) | non | nolann |
| 2 | `app_id` | 6 (par user) | rare | business |
| 3 | `categories` | 31 (taxonomie auto) | oui | nocode18, copywriting |
| 4 | `tags` | libres | a la volee | client-laura, Q2-2026 |
| 5 | graph | auto-extract | auto | (Person)-[FOUNDED]->(Company) |

Details -> [TAXONOMY.md](TAXONOMY.md).

## MCP URL pattern

```
http://<host>:8765/mcp/{agent_id}/http/{user_id}
```

Examples:
- `https://mcp-memory.nocode18.com/mcp/dev-zephly/http/nolann`
- `https://mcp-memory.nocode18.com/mcp/jess-assistant/http/jess`

At the first request from a new `agent_id`, OpenMemory creates the
corresponding `App` row on-the-fly. Same for `user_id`.

## Memory routing (3 mecanismes)

1. **Prefixe explicite** dans `add_memories(text)` : `"[shared] my Twitter is @follox42"` -> route vers app `shared`
2. **App par defaut de l'agent** (= homonyme du `client_name` MCP) si pas de prefixe
3. **Promote/move post-hoc** via `promote_memory(id)` ou `move_memory(id, target_app)`

En parallele, le LLM auto-categorise (niveau 3) avec la taxonomie de `config/categories.yaml`.

## Default ACL (`shared_default: true`)

Apps lisibles par TOUS les agents Nolann automatiquement :
- `shared` (identite, profils sociaux, prefs globales)
- `learn` (connaissances transverses)

Les autres apps -> acces explicite uniquement (via REST API ACL si besoin de granularite).

## Spawning a new agent

1. Pick an `agent_id` (e.g. `ops-nocode18`).
2. Add the MCP URL to your client (`~/.claude/settings.json`):
   ```json
   "ops-nocode18": {
     "type": "http",
     "url": "https://mcp-memory.nocode18.com/mcp/ops-nocode18/http/nolann"
   }
   ```
3. The first call creates the App with default ACL (access to `shared_default` apps + its own app).
4. Optional: restrict scope via REST API.

## Adding a user, app, or category

1. Edit `config/users.yaml`, `config/apps.yaml`, or `config/categories.yaml`.
2. Restart the API container OR run inside the container: `python scripts/seed.py`.
3. The seed is **idempotent** (apps/users), categories cache resets on restart.

## Stack

| Service | Image | Role |
|---|---|---|
| postgres | postgres:16-alpine | metadata (users, apps, ACL, history, categories) |
| qdrant | qdrant/qdrant:v1.12.4 | vector store (semantic search) |
| neo4j | neo4j:5.24-community | graph memory (entities + relations); UI on :7474 |
| openmemory-mcp | mem0/openmemory-mcp | API + MCP server (port 8765) |
| openmemory-ui | local build | Next.js dashboard (port 3000) |

## Graph memory (Neo4j)

Enabled automatically when `NEO4J_URL` is set. mem0 builds an entity-relation
graph alongside the vector store. Inspect via Neo4j Browser on `:7474`
(creds: `neo4j` / `${NEO4J_PASSWORD}`).

## Coolify deployment

- App: `openmemory` (uuid `osqkvaex8ppdnmms3qh7hlgy`)
- Repo: `follox42/mem0` branch `main` (PRs land via `dev`)
- Traefik handles HTTPS + routing
- FQDN: `mcp-memory.nocode18.com` (API), `memory.nocode18.com` (UI)
- Tailscale-only ingress recommended for sensitive data

## Plane tracking

Project `MEM` (OpenMemory Stack):
- MEM-1 Backend multi-user dynamique
- MEM-2 Graph memory Neo4j
- MEM-3 Seed users + apps + ACL
- MEM-4 Outils MCP routing (prefixe + promote/move/tag)
- MEM-5 Notes KB Obsidian
- MEM-6 Plugin Claude Code (hooks auto-memoire) - low priority
- MEM-7 Re-categorization batch endpoint - planned
- MEM-8 UI categories management - planned
