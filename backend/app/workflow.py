"""Server-side workflow rules. Single source of truth for legal status transitions."""

from app.models import  Status  # noqa: F401  (Action imported for clarity)

# Legal forward transitions. Any transition not in this map is rejected.
TRANSITIONS: dict[Status, set[Status]] = {
    Status.OPEN: {Status.IN_PROGRESS},
    Status.IN_PROGRESS: {Status.AWAITING_APPROVAL, Status.OPEN},
    Status.AWAITING_APPROVAL: {Status.RESOLVED, Status.IN_PROGRESS},
    Status.RESOLVED: {Status.CLOSED, Status.IN_PROGRESS},
    Status.CLOSED: set(),  # terminal
}

# Transitions that specifically require the "approve" permission (Lead or Admin).
APPROVAL_TRANSITIONS: set[tuple[Status, Status]] = {
    (Status.AWAITING_APPROVAL, Status.RESOLVED),
}


def is_legal_transition(old: Status, new: Status) -> bool:
    return new in TRANSITIONS.get(old, set())


def requires_approval(old: Status, new: Status) -> bool:
    return (old, new) in APPROVAL_TRANSITIONS