"""Idempotent seed: 3 teams, 10 users (all roles covered), 500 items.

Run inside the container:
    docker compose exec api python -m app.seed
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.auth import hash_password
from app.db import AsyncSessionLocal
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

TEAMS = ["Platform", "Payments", "Customer Success"]

# (email, full_name, team, role). Everyone's password: "password123"
USERS = [
    ("admin@newtonite.test", "Ada Admin", "Platform", Role.ADMIN),
    ("lead.platform@newtonite.test", "Lena Lead", "Platform", Role.LEAD),
    ("member.platform@newtonite.test", "Miles Member", "Platform", Role.MEMBER),
    ("viewer.platform@newtonite.test", "Vera Viewer", "Platform", Role.VIEWER),
    ("lead.payments@newtonite.test", "Leo Lead", "Payments", Role.LEAD),
    ("member.payments@newtonite.test", "Mia Member", "Payments", Role.MEMBER),
    ("viewer.payments@newtonite.test", "Victor Viewer", "Payments", Role.VIEWER),
    ("lead.cs@newtonite.test", "Lara Lead", "Customer Success", Role.LEAD),
    ("member.cs@newtonite.test", "Max Member", "Customer Success", Role.MEMBER),
    ("member2.cs@newtonite.test", "Maya Member", "Customer Success", Role.MEMBER),
]

ITEM_COUNT = 500
PASSWORD = "password123"


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        # teams
        team_map: dict[str, Team] = {}
        for name in TEAMS:
            existing = await session.scalar(select(Team).where(Team.name == name))
            if existing is None:
                t = Team(name=name)
                session.add(t)
                await session.flush()
                team_map[name] = t
            else:
                team_map[name] = existing

        # users + memberships
        user_map: dict[str, User] = {}
        for email, full_name, team_name, role in USERS:
            u = await session.scalar(select(User).where(User.email == email))
            if u is None:
                u = User(email=email, full_name=full_name, password_hash=hash_password(PASSWORD))
                session.add(u)
                await session.flush()
            user_map[email] = u

            m = await session.scalar(
                select(Membership).where(
                    Membership.user_id == u.id,
                    Membership.team_id == team_map[team_name].id,
                )
            )
            if m is None:
                session.add(Membership(user_id=u.id, team_id=team_map[team_name].id, role=role))

        await session.commit()

        # items — only seed if empty (idempotent)
        count = await session.scalar(select(func.count()).select_from(WorkItem))
        if count and count > 0:
            print(f"Items already present ({count}); skipping item seed.")
            return

        rng = random.Random(42)
        now = datetime.now(timezone.utc)
        priorities = list(Priority)
        types = list(ItemType)
        statuses = list(Status)

        all_users = list(user_map.values())

        for i in range(ITEM_COUNT):
            team = team_map[rng.choice(TEAMS)]
            team_members = [u for u in all_users if any(
                m.team_id == team.id for m in []  # placeholder; fall back below
            )] or all_users

            creator = rng.choice(team_members)
            assignee = rng.choice(team_members) if rng.random() < 0.7 else None
            status = rng.choice(statuses)
            if assignee is None and status in (Status.IN_PROGRESS, Status.AWAITING_APPROVAL):
                status = Status.OPEN

            item = WorkItem(
                title=f"{rng.choice(['Fix','Handle','Investigate','Review'])} {rng.choice(['timeout','refund','migration','alert','ticket'])} #{i+1}",
                description="Seeded for pagination testing.",
                type=rng.choice(types),
                priority=rng.choice(priorities),
                status=status,
                team_id=team.id,
                assignee_id=assignee.id if assignee else None,
                created_by_id=creator.id,
                due_date=now + timedelta(days=rng.randint(-5, 20)),
            )
            session.add(item)
            await session.flush()

            session.add(ActivityEvent(
                item_id=item.id,
                actor_id=creator.id,
                kind="created",
                new_value={"status": item.status.value, "priority": item.priority.value},
            ))

        await session.commit()
        print(f"Seeded {ITEM_COUNT} items.")
        print("Login with any of:")
        for email, full_name, team, role in USERS:
            print(f"  {email} / {PASSWORD}  ({role.value} @ {team})")


if __name__ == "__main__":
    asyncio.run(seed())