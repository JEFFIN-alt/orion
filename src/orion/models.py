from enum import StrEnum


class ValidationError(ValueError):
    """Input or state transition is invalid."""


class NotFoundError(ValidationError):
    """The requested record does not exist."""


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TASK_TRANSITIONS = {
    "pending": {"in_progress", "cancelled"},
    "in_progress": {"blocked", "completed", "failed", "pending", "cancelled"},
    "blocked": {"in_progress", "pending", "cancelled"},
    "failed": {"pending", "cancelled"},
    "completed": set(), "cancelled": set(),
}
PROJECT_TRANSITIONS = {
    "active": {"paused", "completed", "cancelled"},
    "paused": {"active", "cancelled"},
    "completed": set(), "cancelled": set(),
}


def required(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be non-empty text")
    return value.strip()
