import os

# USER_ID:
#   - None (default) = multi-user mode. Users created on-the-fly from the MCP
#     path /mcp/{client_name}/http/{user_id}. No global default user.
#   - "<some-id>"   = legacy single-user mode. Default user is created at boot
#     and used by routes that don't carry a user context.
USER_ID = os.getenv("USER") or None

DEFAULT_APP_ID = "openmemory"
