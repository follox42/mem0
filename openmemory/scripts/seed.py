"""
OpenMemory seed script -- idempotent.

Reads config/users.yaml and config/apps.yaml, creates/updates:
- Users (one per person)
- Apps per user (memory zones)
- App metadata: shared_default (readable by all agents of that user)

Run at container boot via docker-compose `command:` (SEED_ON_BOOT=true).
Safe to run multiple times -- checks existence before insert.

Usage:
    python scripts/seed.py              # default config dir
    SEED_CONFIG=/custom/path python ... # override config dir
"""
from __future__ import annotations

import datetime
import os
import sys
import uuid
from pathlib import Path

import yaml

# Make `app` package importable when run from /usr/src/openmemory/scripts/
API_DIR = Path(os.environ.get("OPENMEMORY_API_DIR", "/usr/src/openmemory"))
if not (API_DIR / "app").is_dir():
    # Fallback for local dev (relative to this file)
    API_DIR = Path(__file__).parent.parent / "api"
sys.path.insert(0, str(API_DIR))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import App, User  # noqa: E402

CONFIG_DIR = Path(
    os.environ.get("SEED_CONFIG", "/usr/src/openmemory/config")
)
if not CONFIG_DIR.exists():
    CONFIG_DIR = Path(__file__).parent.parent / "config"


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def load_yaml(name: str) -> dict:
    path = CONFIG_DIR / f"{name}.yaml"
    if not path.exists():
        print(f"[seed] WARN: {path} not found, skipping")
        return {}
    return yaml.safe_load(path.read_text()) or {}


def seed_users(db, cfg: dict) -> int:
    created = 0
    for u in cfg.get("users", []):
        existing = db.query(User).filter(User.user_id == u["id"]).first()
        if existing:
            continue
        user = User(
            id=uuid.uuid4(),
            user_id=u["id"],
            name=u.get("name"),
            metadata_={"description": u.get("description", "")},
            created_at=now_utc(),
        )
        db.add(user)
        created += 1
        print(f"[seed]   + user {u['id']}")
    db.commit()
    return created


def seed_apps(db, cfg: dict) -> int:
    created = 0
    for user_id, apps in cfg.get("apps", {}).items():
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            print(f"[seed] WARN: user {user_id} not found, skipping its apps")
            continue
        for a in apps:
            existing = db.query(App).filter(
                App.owner_id == user.id, App.name == a["name"]
            ).first()
            if existing:
                continue
            app_row = App(
                id=uuid.uuid4(),
                owner_id=user.id,
                name=a["name"],
                description=a.get("description", ""),
                metadata_={
                    "shared_default": bool(a.get("shared_default", False)),
                },
                is_active=True,
                created_at=now_utc(),
            )
            db.add(app_row)
            created += 1
            print(f"[seed]   + app {user_id}/{a['name']}")
    db.commit()
    return created


def main() -> int:
    print(f"[seed] OpenMemory seed starting (config dir: {CONFIG_DIR})...")
    Base.metadata.create_all(bind=engine)

    users_cfg = load_yaml("users")
    apps_cfg = load_yaml("apps")

    db = SessionLocal()
    try:
        n_users = seed_users(db, users_cfg)
        n_apps = seed_apps(db, apps_cfg)
    finally:
        db.close()

    print(f"[seed] Done. {n_users} users created, {n_apps} apps created.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
