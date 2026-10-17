import enum

from app.models import Role


class Action(str, enum.Enum):
    READ = "read"
    CREATE = "create"
    CLAIM = "claim"
    UPDATE = "update"
    TRANSITION = "transition"
    APPROVE = "approve"
    REASSIGN = "reassign"
    DELETE = "delete"
    COMMENT = "comment"


# The one and only permission matrix. Add a row here to grant a new permission.
# Edit this file only — do not sprinkle `if role == ...` in routers.
ACTION_MATRIX: dict[Role, set[Action]] = {
    Role.VIEWER: {Action.READ, Action.COMMENT},
    Role.MEMBER: {Action.READ, Action.CREATE, Action.CLAIM, Action.UPDATE,
                  Action.TRANSITION, Action.COMMENT},
    Role.LEAD: {Action.READ, Action.CREATE, Action.CLAIM, Action.UPDATE,
                Action.TRANSITION, Action.APPROVE, Action.REASSIGN, Action.COMMENT},
    Role.ADMIN: {Action.READ, Action.CREATE, Action.CLAIM, Action.UPDATE,
                 Action.TRANSITION, Action.APPROVE, Action.REASSIGN, Action.DELETE,
                 Action.COMMENT},
}


def can(user_roles: dict, item_team_id, action: Action) -> bool:
    """Return True iff the user has `action` rights on the given team."""
    role = user_roles.get(item_team_id)
    if role is None:
        return False
    return action in ACTION_MATRIX[role]