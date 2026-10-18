"""
Work-item service layer.

EVERY mutation here writes its activity event in the SAME database
transaction as the item change. This is the guarantee: history can
never disagree with the item.

Concurrency control:
  - claim:      conditional UPDATE ... WHERE assignee_id IS NULL (row-level atomic)
  - edit:       optimistic lock via version column, mismatch -> 409
  - idempotency: unique (user_id, key) row inserted in the same txn
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ActivityEvent,
    IdempotencyKey,
    Priority,
    Status,
    Team,
    User,
    WorkItem,
)
from app.permissions import Action, can
from app.schemas import ItemCreate, ItemUpdate
from app.workflow import is_legal_transition, requires_approval


# ---------------- helpers ----------------

def _forbidden() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not permitted")


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")


def _conflict(detail: str, item: WorkItem | None = None) -> HTTPException:
    payload: dict = {"detail": detail}
    if item is not None:
        payload["current"] = {
            "id": str(item.id),
            "version": item.version,
            "status": item.status.value,
            "assignee_id": str(item.assignee_id) if item.assignee_id else None,
        }
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=payload)


async def _require_item(session: AsyncSession, item_id: uuid.UUID) -> WorkItem:
    item = await session.get(WorkItem, item_id)
    if item is None:
        raise _not_found()
    return item


def _require(user_roles: dict, team_id: uuid.UUID, action: Action) -> None:
    if not can(user_roles, team_id, action):
        raise _forbidden()


async def _log(
    session: AsyncSession,
    item_id: uuid.UUID,
    actor_id: uuid.UUID,
    kind: str,
    *,
    old: dict | None = None,
    new: dict | None = None,
    note: str | None = None,
) -> None:
    session.add(ActivityEvent(
        item_id=item_id,
        actor_id=actor_id,
        kind=kind,
        old_value=old,
        new_value=new,
        note=note,
    ))


# ---------------- read ----------------

async def get_item(
    session: AsyncSession, item_id: uuid.UUID, user: User, user_roles: dict,
) -> WorkItem:
    item = await _require_item(session, item_id)
    _require(user_roles, item.team_id, Action.READ)
    return item


async def list_items(
    session: AsyncSession,
    user: User,
    user_roles: dict,
    *,
    status_: Status | None = None,
    priority: Priority | None = None,
    assignee_me: bool = False,
    q: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> tuple[list[WorkItem], str | None]:
    """
    List items visible to the user (any team they belong to).
    Uses keyset cursor on (created_at DESC, id DESC) — no OFFSET.
    """
    if not user_roles:
        return [], None

    team_ids = list(user_roles.keys())
    stmt = select(WorkItem).where(WorkItem.team_id.in_(team_ids))

    if status_ is not None:
        stmt = stmt.where(WorkItem.status == status_)
    if priority is not None:
        stmt = stmt.where(WorkItem.priority == priority)
    if assignee_me:
        stmt = stmt.where(WorkItem.assignee_id == user.id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(WorkItem.title.ilike(like), WorkItem.description.ilike(like)))

    # keyset cursor: "created_at_iso|id"
    if cursor:
        try:
            ts_str, id_str = cursor.split("|", 1)
            cur_ts = datetime.fromisoformat(ts_str)
            cur_id = uuid.UUID(id_str)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="invalid cursor")

        stmt = stmt.where(
            or_(
                WorkItem.created_at < cur_ts,
                and_(WorkItem.created_at == cur_ts, WorkItem.id < cur_id),
            )
        )

    stmt = stmt.order_by(WorkItem.created_at.desc(), WorkItem.id.desc()).limit(limit + 1)

    rows = (await session.execute(stmt)).scalars().all()

    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = f"{last.created_at.isoformat()}|{last.id}"
        rows = rows[:limit]

    return list(rows), next_cursor


async def get_activity(
    session: AsyncSession, item_id: uuid.UUID, user: User, user_roles: dict,
) -> list[ActivityEvent]:
    item = await _require_item(session, item_id)
    _require(user_roles, item.team_id, Action.READ)
    stmt = (
        select(ActivityEvent)
        .where(ActivityEvent.item_id == item_id)
        .order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc())
        .limit(200)
    )
    return list((await session.execute(stmt)).scalars().all())


# ---------------- create (idempotent) ----------------

async def create_item(
    session: AsyncSession,
    payload: ItemCreate,
    user: User,
    user_roles: dict,
    idempotency_key: str | None,
) -> tuple[WorkItem, bool]:
    """
    Returns (item, was_replayed).
    If idempotency_key is provided:
      - if a response for (user, key) already exists -> replay it
      - otherwise write the response in the SAME transaction as the item
    """
    if not can(user_roles, payload.team_id, Action.CREATE):
        raise _forbidden()

    # Verify the team exists (a foreign key would also catch this, but a clean 404 is nicer).
    team = await session.get(Team, payload.team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")

    request_hash = hashlib.sha256(
        json.dumps(payload.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()

    # Replay if same key
    if idempotency_key:
        existing = await session.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.user_id == user.id,
                IdempotencyKey.key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise HTTPException(
                    status_code=409,
                    detail="idempotency key reused with different payload",
                )
            # Load the item the stored response refers to.
            stored_item_id = uuid.UUID(existing.response_json["id"])
            replayed = await session.get(WorkItem, stored_item_id)
            if replayed is None:
                raise HTTPException(status_code=500, detail="stored idempotent response references missing item")
            return replayed, True

    async with session.begin_nested():
        item = WorkItem(
            title=payload.title,
            description=payload.description,
            type=payload.type,
            priority=payload.priority,
            status=Status.OPEN,
            team_id=payload.team_id,
            assignee_id=payload.assignee_id,
            created_by_id=user.id,
            due_date=payload.due_date,
        )
        session.add(item)
        await session.flush()

        await _log(
            session, item.id, user.id, "created",
            new={"status": item.status.value, "priority": item.priority.value,
                 "title": item.title},
        )

        if idempotency_key:
            session.add(IdempotencyKey(
                key=idempotency_key,
                user_id=user.id,
                request_hash=request_hash,
                response_json={"id": str(item.id)},
                status_code=201,
            ))

    await session.commit()
    await session.refresh(item)
    return item, False


# ---------------- claim (atomic) ----------------

async def claim_item(
    session: AsyncSession, item_id: uuid.UUID, user: User, user_roles: dict,
) -> WorkItem:
    """
    Conditional UPDATE — only succeeds if assignee_id IS NULL.
    Two concurrent requests: exactly one wins, the other gets 409.
    """
    item = await _require_item(session, item_id)
    _require(user_roles, item.team_id, Action.CLAIM)

    stmt = (
        update(WorkItem)
        .where(WorkItem.id == item_id, WorkItem.assignee_id.is_(None))
        .values(assignee_id=user.id, version=WorkItem.version + 1)
        .returning(WorkItem)
    )
    result = await session.execute(stmt)
    updated = result.scalar_one_or_none()

    if updated is None:
        # Snapshot the fields we need BEFORE invalidating the session.
        # (MissingGreenlet otherwise fires when _conflict reads .version.)
        await session.refresh(item)
        snapshot = {
            "id": str(item.id),
            "version": item.version,
            "status": item.status.value,
            "assignee_id": str(item.assignee_id) if item.assignee_id else None,
        }
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "item already claimed", "current": snapshot},
        )

    await _log(
        session, item_id, user.id, "claimed",
        old={"assignee_id": None},
        new={"assignee_id": str(user.id)},
    )
    await session.commit()
    await session.refresh(updated)
    return updated


# ---------------- edit with version lock ----------------

async def update_item(
    session: AsyncSession,
    item_id: uuid.UUID,
    payload: ItemUpdate,
    user: User,
    user_roles: dict,
) -> WorkItem:
    item = await _require_item(session, item_id)
    _require(user_roles, item.team_id, Action.UPDATE)

    if item.version != payload.expected_version:
        snapshot = {
            "id": str(item.id),
            "version": item.version,
            "status": item.status.value,
            "assignee_id": str(item.assignee_id) if item.assignee_id else None,
        }
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "detail": f"stale version (you sent {payload.expected_version}, current is {item.version})",
                "current": snapshot,
            },
        )

    changes: dict = {}
    new_values: dict = {}
    old_values: dict = {}

    if payload.title is not None and payload.title != item.title:
        changes["title"] = payload.title
        new_values["title"] = payload.title
    if payload.description is not None and payload.description != item.description:
        changes["description"] = payload.description
    if payload.priority is not None and payload.priority != item.priority:
        changes["priority"] = payload.priority
        new_values["priority"] = payload.priority.value
        old_values["priority"] = item.priority.value
    if payload.due_date is not None and payload.due_date != item.due_date:
        changes["due_date"] = payload.due_date

    if not changes:
        return item

    changes["version"] = WorkItem.version + 1

    stmt = (
        update(WorkItem)
        .where(WorkItem.id == item_id, WorkItem.version == payload.expected_version)
        .values(**changes)
        .returning(WorkItem)
    )
    result = await session.execute(stmt)
    updated = result.scalar_one_or_none()

    if updated is None:
        await session.refresh(item)
        snapshot = {
            "id": str(item.id),
            "version": item.version,
            "status": item.status.value,
            "assignee_id": str(item.assignee_id) if item.assignee_id else None,
        }
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "concurrent update", "current": snapshot},
        )

    await _log(
        session, item_id, user.id, "updated",
        old=old_values or None,
        new=new_values or None,
    )
    await session.commit()
    await session.refresh(updated)
    return updated


# ---------------- workflow transition ----------------
async def transition_item(
    session: AsyncSession,
    item_id: uuid.UUID,
    to_status: Status,
    note: str | None,
    user: User,
    user_roles: dict,
) -> WorkItem:
    item = await _require_item(session, item_id)
    _require(user_roles, item.team_id, Action.TRANSITION)

    if not is_legal_transition(item.status, to_status):
        raise HTTPException(
            status_code=422,
            detail=f"illegal transition {item.status.value} -> {to_status.value}",
        )

    if requires_approval(item.status, to_status):
        _require(user_roles, item.team_id, Action.APPROVE)

    expected_version = item.version
    old_status_value = item.status.value

    stmt = (
        update(WorkItem)
        .where(WorkItem.id == item_id, WorkItem.version == expected_version)
        .values(status=to_status, version=WorkItem.version + 1)
        .returning(WorkItem)
    )
    result = await session.execute(stmt)
    updated = result.scalar_one_or_none()
    if updated is None:
        await session.refresh(item)
        snapshot = {
            "id": str(item.id),
            "version": item.version,
            "status": item.status.value,
            "assignee_id": str(item.assignee_id) if item.assignee_id else None,
        }
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "item changed while transitioning", "current": snapshot},
        )

    await _log(
        session, item_id, user.id, "status_changed",
        old={"status": old_status_value},
        new={"status": to_status.value},
        note=note,
    )
    await session.commit()
    await session.refresh(updated)
    return updated


# ---------------- comment ----------------

async def add_comment(
    session: AsyncSession,
    item_id: uuid.UUID,
    body: str,
    user: User,
    user_roles: dict,
) -> ActivityEvent:
    item = await _require_item(session, item_id)
    _require(user_roles, item.team_id, Action.COMMENT)

    async with session.begin_nested():
        event = ActivityEvent(
            item_id=item_id,
            actor_id=user.id,
            kind="comment",
            note=body,
        )
        session.add(event)
    await session.commit()
    await session.refresh(event)
    return event