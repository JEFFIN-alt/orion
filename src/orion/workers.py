"""Trusted deterministic workers. Task input cannot choose imports or callables."""
from collections import Counter
from dataclasses import dataclass
from typing import Callable
from .models import ValidationError


def project_report(snapshot: dict) -> dict:
    return {"schema_version": 1, "snapshot_at": snapshot["snapshot_at"],
            "project": snapshot["project"], "tasks": snapshot["tasks"],
            "counts": dict(Counter(t["status"] for t in snapshot["tasks"]))}


def validate_report(snapshot: dict, output: dict) -> None:
    if not isinstance(output, dict) or output != project_report(snapshot):
        raise ValidationError("Worker output does not match the captured project records")


@dataclass(frozen=True)
class Worker:
    identifier: str
    name: str
    responsibility: str
    handler: Callable[[dict], dict]
    validator: Callable[[dict, dict], None]
    version: str = "1"
    expected_input: str = "Consistent project/task snapshot supplied by engine"
    expected_output: str = "JSON report with project, tasks, state counts and snapshot time"
    capabilities: tuple = ("read supplied snapshot", "return JSON")
    completion_conditions: str = "Output exactly matches source snapshot; artifact saved and read back"

    def describe(self) -> dict:
        return {key: value for key, value in vars(self).items() if key not in ('handler', 'validator')}


REGISTRY = {"project-status": Worker("project-status", "Project status report", "Summarize actual stored records", project_report, validate_report)}


def resolve(worker_id: str, registry=None) -> Worker:
    try:
        return (REGISTRY if registry is None else registry)[worker_id]
    except (KeyError, TypeError) as exc:
        raise ValidationError(f"Unknown registered worker: {worker_id}") from exc
