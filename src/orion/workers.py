"""Trusted deterministic workers. Task input cannot choose imports or callables."""
from collections import Counter
from dataclasses import dataclass
from typing import Callable
from .models import ValidationError
from .csv_worker import profile, validate_output


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
    required_verifier: str | None = None
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


REGISTRY["csv-profile"] = Worker("csv-profile", "CSV profile", "Profile an explicitly imported CSV", profile, validate_output,
    expected_input="Registered input ID, digest-bound bytes, explicit limits",
    expected_output="JSON dataset structure, missing counts and decimal numeric summaries",
    capabilities=("read supplied bounded CSV bytes", "return JSON"),
    completion_conditions="Saved artifact passes separate CSV verification", required_verifier="csv-independent")


from .research_sources import collect, validate_packet
REGISTRY['research-collect'] = Worker('research-collect', 'Public technical evidence collection',
    'Collect bounded Crossref and GitHub evidence without synthesis', collect, validate_packet,
    required_verifier='research-independent', expected_input='Approved bounded question and source configuration',
    expected_output='JSON evidence packet with captured public API responses and provenance',
    capabilities=('HTTPS GET to fixed Crossref/GitHub API endpoints', 'read supplied configuration', 'return JSON'),
    completion_conditions='At least one provider search succeeds; saved packet passes independent provenance checks')


from .synthesis_worker import synthesize, validate_envelope
REGISTRY['research-synthesize'] = Worker('research-synthesize','Evidence-grounded research analyst',
    'Analyse a verified research packet through the configured language model',synthesize,validate_envelope,
    required_verifier='synthesis-independent',expected_input='Verified research execution, bounded excerpts, approved model/configuration',
    expected_output='Separate synthesis envelope with strict cited JSON analysis and actual provider metadata',
    capabilities=('call configured provider through existing interface','read supplied evidence projection','return JSON'),
    completion_conditions='Provider completes and independent schema/provenance/citation verification passes; factual quality requires human review')
