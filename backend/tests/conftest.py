"""
Pytest fixtures.

Strategy:
  - Create `newtonite_test` DB ONCE at session start via a SYNC subprocess call
    (psql via docker compose). No async fixture, no event-loop scope conflicts.
  - Per-test: fresh engine (NullPool), drop+create tables, run test, drop tables,
    dispose engine. Fully isolated.
"""

import os
import subprocess
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.auth import hash_password
from app.db import Base, get_session
from app.main import app
from app.models import (
    ActivityEvent,
    ItemType,
    Membership,
    Priority,
    Role,
    Status,
    Team,
    User,
    WorkItem,
)

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://newtonite:newtonite_dev_pw@db:5432/newtonite_test",
)

PASSWORD = "password123"


# ---------- create test DB once, using a sync subprocess ----------

def _create_test_db_if_missing() -> None:
    """Idempotent. Runs a shell psql command; no async/event loop involved."""
    check = subprocess.run(
        [
            "psql",
            "-h", "db",
            "-U", "newtonite",
            "-d", "postgres",
            "-tAc",
            "SELECT 1 FROM pg_database WHERE datname = 'newtonite_test'",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "PGPASSWORD": "newtonite_dev_pw"},
    )
    if check.stdout.strip() == "1":
        return
    subprocess.run(
        [
            "psql",
            "-h", "db",
            "-U", "newtonite",
            "-d", "postgres",
            "-c",
            "CREATE DATABASE newtonite_test",
        ],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PGPASSWORD": "newtonite_dev_pw"},
    )


@pytest.fixture(scope="session", autouse=True)
def _ensure_test_db():
    _create_test_db_if_missing()
    yield


# ---------- per-test engine + schema ----------

@pytest_asyncio.fixture
async def db_engine(_ensure_test_db) -> AsyncGenerator:
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    SessionLocal = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as s:
        yield s


# ---------- app client with overridden DB dependency ----------

@pytest_asyncio.fixture
async def client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    SessionLocal = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def _override():
        async with SessionLocal() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------- seeded data ----------

@pytest_asyncio.fixture
async def seeded(db_engine):
    SessionLocal = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as s:
        platform = Team(name="Platform")
        payments = Team(name="Payments")
        s.add_all([platform, payments])
        await s.flush()

        admin = User(email="admin@t.test", full_name="Ada Admin", password_hash=hash_password(PASSWORD))
        lead = User(email="lead@t.test", full_name="Lena Lead", password_hash=hash_password(PASSWORD))
        member = User(email="member@t.test", full_name="Miles Member", password_hash=hash_password(PASSWORD))
        viewer = User(email="viewer@t.test", full_name="Vera Viewer", password_hash=hash_password(PASSWORD))
        outside = User(email="outside@t.test", full_name="Otis Outside", password_hash=hash_password(PASSWORD))
        s.add_all([admin, lead, member, viewer, outside])
        await s.flush()

        s.add_all([
            Membership(user_id=admin.id, team_id=platform.id, role=Role.ADMIN),
            Membership(user_id=lead.id, team_id=platform.id, role=Role.LEAD),
            Membership(user_id=member.id, team_id=platform.id, role=Role.MEMBER),
            Membership(user_id=viewer.id, team_id=platform.id, role=Role.VIEWER),
            Membership(user_id=outside.id, team_id=payments.id, role=Role.MEMBER),
        ])
        await s.flush()

        items = []
        for i in range(3):
            it = WorkItem(
                title=f"item-{i}",
                description="",
                type=ItemType.TASK,
                priority=Priority.MEDIUM,
                status=Status.OPEN,
                team_id=platform.id,
                created_by_id=member.id,
            )
            s.add(it)
            items.append(it)
        await s.flush()

        for it in items:
            s.add(ActivityEvent(
                item_id=it.id, actor_id=member.id, kind="created",
                new_value={"status": "open"},
            ))

        await s.commit()

        return {
            "platform_id": str(platform.id),
            "payments_id": str(payments.id),
            "admin_id": str(admin.id),
            "lead_id": str(lead.id),
            "member_id": str(member.id),
            "viewer_id": str(viewer.id),
            "outside_id": str(outside.id),
            "items": [str(i.id) for i in items],
            "emails": {
                "admin": "admin@t.test",
                "lead": "lead@t.test",
                "member": "member@t.test",
                "viewer": "viewer@t.test",
                "outside": "outside@t.test",
            },
        }


async def _login(client: AsyncClient, email: str) -> str:
    r = await client.post(
        "/auth/login",
        data={"username": email, "password": PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest_asyncio.fixture
async def tokens(client, seeded) -> dict:
    out = {}
    for role, email in seeded["emails"].items():
        out[role] = await _login(client, email)
    return out