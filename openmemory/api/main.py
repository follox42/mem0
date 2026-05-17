import datetime
from uuid import uuid4

from app.config import DEFAULT_APP_ID, USER_ID
from app.database import Base, SessionLocal, engine
from app.mcp_server import setup_mcp_server
from app.models import App, User
from app.routers import (apps_router, backup_router, config_router,
                         identity_router, memories_router, stats_router)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_pagination import add_pagination

app = FastAPI(title="OpenMemory API")


# Rewrite http:// → https:// in Location headers for ALL responses.
# Reason: Starlette's redirect_slashes (and other RedirectResponse callers)
# generate Location URLs from scope['scheme'], which is "http" when uvicorn
# is behind Traefik. ProxyHeadersMiddleware (the recommended fix) didn't
# take effect here — middleware ordering inside FastAPI puts it AFTER
# router decision, so the redirect is built before scheme is rewritten.
# This pure-ASGI middleware sits at the outermost layer and rewrites the
# Location bytes in flight. Bulletproof.
class ForceHTTPSLocationMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        async def _send(message):
            if message.get("type") == "http.response.start":
                new_headers = []
                for name, value in message.get("headers", []):
                    if name.lower() == b"location" and value.startswith(b"http://"):
                        value = b"https://" + value[len(b"http://"):]
                    new_headers.append((name, value))
                message["headers"] = new_headers
            await send(message)

        await self.app(scope, receive, _send)


app.add_middleware(ForceHTTPSLocationMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://memory.nocode18.com",
        "https://mcp-memory.nocode18.com",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create all tables
Base.metadata.create_all(bind=engine)


def create_default_user():
    """Legacy single-user bootstrap.

    No-op in multi-user mode (USER_ID is None). Users are then created on-the-fly
    from the MCP path /mcp/{client_name}/http/{user_id}, or via scripts/seed.py.
    """
    if not USER_ID:
        return
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == USER_ID).first()
        if not user:
            user = User(
                id=uuid4(),
                user_id=USER_ID,
                name="Default User",
                created_at=datetime.datetime.now(datetime.UTC)
            )
            db.add(user)
            db.commit()
    finally:
        db.close()


def create_default_app():
    """Legacy single-user bootstrap. No-op in multi-user mode."""
    if not USER_ID:
        return
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == USER_ID).first()
        if not user:
            return

        existing_app = db.query(App).filter(
            App.name == DEFAULT_APP_ID,
            App.owner_id == user.id
        ).first()

        if existing_app:
            return

        app_row = App(
            id=uuid4(),
            name=DEFAULT_APP_ID,
            owner_id=user.id,
            created_at=datetime.datetime.now(datetime.UTC),
            updated_at=datetime.datetime.now(datetime.UTC),
        )
        db.add(app_row)
        db.commit()
    finally:
        db.close()


# Bootstrap (no-op in multi-user mode)
create_default_user()
create_default_app()

# Setup MCP server
setup_mcp_server(app)

# Include routers
app.include_router(memories_router)
app.include_router(apps_router)
app.include_router(stats_router)
app.include_router(config_router)
app.include_router(backup_router)
app.include_router(identity_router)

# Add pagination support
add_pagination(app)
