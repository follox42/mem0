# Identity Detection System (MEM-7)

> Dynamic identification of which household person (Nolann / Jess / Yoann / Matt / Djamila) is talking to an OpenMemory agent. Cold/warm/hot phases with continuous learning.

**Plane:** MEM-7
**System prompt template:** `openmemory/prompts/identity-aware-agent.md`
**Detailed design:** see KB note `projects/openmemory-stack/identity-detection-design-and-code.md` in the Obsidian vault.

---

## Why

5 persons in the household share the OpenMemory stack. Each agent **must** know who is talking before acting, otherwise it leaks Nolann's memories to others (or vice-versa). Manual identification at every session is friction. Solution: a learned classifier that:

- starts cold (asks explicitly via menu)
- learns from each confirmation
- ends silent (guesses with high confidence)

## Architecture

```
+---------------------------------------------+
| Agent (Claude Code, Claude.com, ...)        |
+--+------------------------------------------+
   |
   | 1. identify_person(message_text)
   v
+--+------------------------------------------+
| MCP tool identify_person                    |
|   -> POST /api/v1/identity/guess            |
|   <- {predictions, top_confidence, suggestion}|
+--+------------------------------------------+
   |
   v
+---------------------------------------------+
| services/identity_detector.py               |
|   Stage 1: vector kNN (cosine vs samples)   |
|   Stage 2: LLM scorer if Stage 1 ambiguous  |
+--+------------------------------------------+
   |
   v top_confidence-based suggestion:
   |   >= 0.85 -> accept (silent)
   |   0.50-0.85 -> confirm with user
   |   < 0.50 -> ask 5-choices menu
   v
+---------------------------------------------+
| 2. confirm_identity(user_id, message_text)  |
|   -> POST /api/v1/identity/confirm          |
|   -> insert IdentityMessage + update         |
|      IdentityProfile (running mean embedding)|
+---------------------------------------------+
```

## Three phases of maturity

| Phase | Confirmed samples per user | Behavior |
|---|---|---|
| **Cold** | < 10 | Stage 2 LLM scorer only (weak signal). Always asks via menu. |
| **Warm** | 10 - 200 | Stage 1 vector kNN. Asks for confirmation on borderline guesses (0.50-0.85). |
| **Hot** | > 200 | Vector kNN reliable. Accepts silently when >= 0.85. |

## Signals used

1. **Style embedding** (text-embedding-3-small): the message vector is compared (cosine) to the last 200 confirmed messages of each user. Captures style + vocabulary + topics.
2. **LLM scorer** (gpt-4o-mini) when Stage 1 top-1 vs top-2 gap < 0.10. The LLM reads the message + each candidate's profile summary and scores 0..1.
3. **Style signature** (V2 ticket): avg sentence length, anglicism frequency, typo rate, top categories. Aggregated in `IdentityProfile.style_signature`.

## Schema (Postgres)

```sql
CREATE TABLE identity_profiles (
    id UUID PRIMARY KEY,
    user_id VARCHAR REFERENCES users(user_id),
    sample_count INT DEFAULT 0,
    embedding_mean JSONB,          -- running average of confirmed embeddings
    style_signature JSONB DEFAULT '{}',
    top_categories JSONB DEFAULT '[]',
    updated_at TIMESTAMP
);

CREATE TABLE identity_messages (
    id UUID PRIMARY KEY,
    user_id VARCHAR REFERENCES users(user_id),
    message_text TEXT NOT NULL,
    embedding JSONB NOT NULL,
    confirmed BOOLEAN DEFAULT TRUE,
    confidence_at_capture FLOAT,
    created_at TIMESTAMP
);
```

Auto-created at boot by `Base.metadata.create_all(bind=engine)` in `main.py`.

## REST API

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/identity/guess` | POST | Rank candidates for a message |
| `/api/v1/identity/confirm` | POST | Record a confirmed (user_id, message) pair |
| `/api/v1/identity/profiles` | GET | List profiles + sample counts |

### Example: guess
```bash
curl -X POST https://mcp-memory.nocode18.com/api/v1/identity/guess \
  -H "Content-Type: application/json" \
  -d '{"message_text": "j ai deploye un nouveau MCP"}'

# {
#   "predictions": [
#     {"user_id": "nolann", "confidence": 0.81, "reasoning": "max cosine over 42 confirmed samples"},
#     {"user_id": "jess",   "confidence": 0.21, "reasoning": "max cosine over 5 confirmed samples"},
#     ...
#   ],
#   "top_user_id": "nolann",
#   "top_confidence": 0.81,
#   "suggestion": "confirm"
# }
```

### Example: confirm
```bash
curl -X POST https://mcp-memory.nocode18.com/api/v1/identity/confirm \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "nolann",
    "message_text": "j ai deploye un nouveau MCP",
    "confidence_at_capture": 0.81
  }'
```

## MCP tools

Exposed via the standard MCP path `/mcp/{agent_id}/http/{user_id}`:

- `identify_person(message_text: str) -> str` — returns JSON with predictions + suggestion
- `confirm_identity(user_id: str, message_text: str, confidence_at_capture: float = None) -> str`

## Seeding (cold start)

Before the model learns, you can manually seed samples per user to bootstrap the warm phase.

```bash
# Nolann (~50 messages with his typical style)
for msg in "j ai bosse sur openfang" "deploy zephly ok" "MRR Stripe +12%" \
           "ftmo challenge en cours" "MCP linkedin shipped" ...; do
  curl -X POST https://mcp-memory.nocode18.com/api/v1/identity/confirm \
    -H "Content-Type: application/json" \
    -d "{\"user_id\": \"nolann\", \"message_text\": \"$msg\"}"
done

# Same for jess, yoann, matt, djamila with their typical style/topics
```

## Test plan

```bash
# 1. After deploy, verify tables created
docker exec openmemory-postgres-1 psql -U openmemory -d openmemory \
  -c "\dt identity*"

# 2. Cold guess (no samples yet) -> LLM-only, weak confidence
curl -X POST .../api/v1/identity/guess -d '{"message_text": "salut ca va ?"}'

# 3. Seed a few samples for nolann + jess
# (see Seeding section)

# 4. Re-guess a Nolann-style message
curl -X POST .../api/v1/identity/guess \
  -d '{"message_text": "MCP deploy en cours sur Coolify"}'
# Expected: top = nolann, confidence rising

# 5. List profiles
curl .../api/v1/identity/profiles
```

## System prompt for agents

See `openmemory/prompts/identity-aware-agent.md`. Inject this as a prefix to ANY agent's system prompt.

## Risks & limits (V1)

- **Cost**: ~$0.0001 per `identify_person` (one OpenAI embedding + optional LLM call). Negligible for personal scale.
- **Cold start**: needs ~50 confirmed samples per user before warm phase is reliable. Use the seeding script.
- **Style drift**: if a person changes style (fatigue, mood), V1 doesn't decay old samples. → V2 ticket.
- **Adversarial**: someone could mimic another's style. → V2: device-bound auth on Tailscale.
- **Privacy**: messages stored in clear in Postgres. OK behind Tailscale; encrypt at rest if exposed publicly (V2).

## Roadmap

| Status | Item | Plane |
|---|---|---|
| done | Schema + service + REST + MCP tools | MEM-7 |
| done | System prompt template | MEM-7 |
| pending | Initial 5x50 sample seed | MEM-7 |
| pending | Style signature extraction (sentence len, anglicisms) | V2 |
| pending | Sample decay (older samples weigh less) | V2 |
| pending | Device-bound auth strong layer for `perso` app | V2 |
| pending | UI page `/settings/identity` with confusion matrix | V2 |
