FROM python:3.12-slim

LABEL org.opencontainers.image.name="mem0/openmemory-mcp"

WORKDIR /usr/src/openmemory

# Build context is openmemory/ (parent of api/), so paths are relative to that.
COPY api/requirements.txt .
RUN pip install -r requirements.txt && pip install pyyaml

# Copy the API source (FastAPI app + mem0 wrappers).
COPY api/config.json .
COPY api/ .

# Copy the multi-user config (users/apps/categories YAML) and the seed
# script directly into the image so they exist regardless of how Coolify
# resolves volume mounts.
COPY config /usr/src/openmemory/config
COPY scripts /usr/src/openmemory/scripts

EXPOSE 8765
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8765"]
