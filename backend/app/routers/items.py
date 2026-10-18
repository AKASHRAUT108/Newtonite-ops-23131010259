"""Item HTTP endpoints. Thin wrappers over app.services.items."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, get_user_roles
from app.db import get_session
from app.models import Priority, Status, User
from app.schemas import (
    ActivityRead,
    ItemCreate,
    ItemPage,
    ItemRead,
    ItemUpdate,
    TransitionRequest,
)
from app.services import items as svc

router = APIRouter(prefix="/items", tags=["items"])


# ---- dependencies ----

async def _ctx(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> tuple[User, dict, AsyncSession]:
    roles = await get_user_roles(user, session)
    return user, roles, session


# ---- read ----

@router.get("", response_model=ItemPage)
async def list_items(
    ctx: Annotated[tuple[User, dict, AsyncSession], Depends(_ctx)],
    status_: Status | None = Query(default=None, alias="status"),
    priority: Priority | None = Query(default=None),
    assignee_me: bool = Query(default=False),
    q: str | None = Query(default=None, max_length=200),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    user, roles, session = ctx
    rows, next_cursor = await svc.list_items(
        session, user, roles,
        status_=status_, priority=priority,
        assignee_me=assignee_me, q=q, cursor=cursor, limit=limit,
    )
    return ItemPage(
        items=[ItemRead.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )


@router.get("/{item_id}", response_model=ItemRead)
async def get_item(
    item_id: uuid.UUID,
    ctx: Annotated[tuple[User, dict, AsyncSession], Depends(_ctx)],
):
    user, roles, session = ctx
    item = await svc.get_item(session, item_id, user, roles)
    return ItemRead.model_validate(item)


@router.get("/{item_id}/activity", response_model=list[ActivityRead])
async def get_activity(
    item_id: uuid.UUID,
    ctx: Annotated[tuple[User, dict, AsyncSession], Depends(_ctx)],
):
    user, roles, session = ctx
    events = await svc.get_activity(session, item_id, user, roles)
    return [ActivityRead.model_validate(e) for e in events]


# ---- create (idempotent) ----

@router.post("", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
async def create_item(
    payload: ItemCreate,
    ctx: Annotated[tuple[User, dict, AsyncSession], Depends(_ctx)],
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    user, roles, session = ctx
    item, replayed = await svc.create_item(session, payload, user, roles, idempotency_key)
    return ItemRead.model_validate(item)


# ---- claim (atomic) ----

@router.post("/{item_id}/claim", response_model=ItemRead)
async def claim_item(
    item_id: uuid.UUID,
    ctx: Annotated[tuple[User, dict, AsyncSession], Depends(_ctx)],
):
    user, roles, session = ctx
    item = await svc.claim_item(session, item_id, user, roles)
    return ItemRead.model_validate(item)


# ---- edit (version-locked) ----

@router.patch("/{item_id}", response_model=ItemRead)
async def update_item(
    item_id: uuid.UUID,
    payload: ItemUpdate,
    ctx: Annotated[tuple[User, dict, AsyncSession], Depends(_ctx)],
):
    user, roles, session = ctx
    item = await svc.update_item(session, item_id, payload, user, roles)
    return ItemRead.model_validate(item)


# ---- workflow transition ----

@router.post("/{item_id}/transition", response_model=ItemRead)
async def transition_item(
    item_id: uuid.UUID,
    payload: TransitionRequest,
    ctx: Annotated[tuple[User, dict, AsyncSession], Depends(_ctx)],
):
    user, roles, session = ctx
    item = await svc.transition_item(
        session, item_id, payload.to_status, payload.note, user, roles,
    )
    return ItemRead.model_validate(item)


# ---- comment ----

@router.post("/{item_id}/comment", response_model=ActivityRead, status_code=status.HTTP_201_CREATED)
async def add_comment(
    item_id: uuid.UUID,
    payload: dict,
    ctx: Annotated[tuple[User, dict, AsyncSession], Depends(_ctx)],
):
    body = (payload or {}).get("body", "").strip()
    if not body:
        raise HTTPException(status_code=422, detail="comment body is required")
    user, roles, session = ctx
    event = await svc.add_comment(session, item_id, body, user, roles)
    return ActivityRead.model_validate(event)