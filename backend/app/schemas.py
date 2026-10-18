"""Pydantic request/response models. Kept separate from ORM models."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import ItemType, Priority, Status


# ---------- Work item ----------

class ItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    type: ItemType
    priority: Priority = Priority.MEDIUM
    team_id: uuid.UUID
    assignee_id: uuid.UUID | None = None
    due_date: datetime | None = None


class ItemUpdate(BaseModel):
    """Version is REQUIRED — server rejects stale writes."""
    expected_version: int
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    priority: Priority | None = None
    due_date: datetime | None = None


class ItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    type: ItemType
    priority: Priority
    status: Status
    team_id: uuid.UUID
    assignee_id: uuid.UUID | None
    created_by_id: uuid.UUID
    due_date: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class TransitionRequest(BaseModel):
    to_status: Status
    note: str | None = None


# ---------- Activity ----------

class ActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    item_id: uuid.UUID
    actor_id: uuid.UUID
    kind: str
    old_value: dict | None
    new_value: dict | None
    note: str | None
    created_at: datetime


# ---------- Pagination ----------

class ItemPage(BaseModel):
    items: list[ItemRead]
    next_cursor: str | None