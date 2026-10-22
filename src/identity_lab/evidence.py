"""Evaluate real observations without conflating denials and propagation."""

from dataclasses import asdict, dataclass
from typing import Any

from .catalog import PATTERNS


@dataclass(frozen=True)
class Result:
    pattern: str
    configuration: str
    status: str
    reason: str
    observation: str
    expectation: str = "preserve-user"

    def public(self) -> dict[str, str]:
        return asdict(self)


def extract_probe(value: Any) -> dict[str, Any]:
    """Find exactly one probe through Responses/MCP/A2A JSON envelopes."""
    import json

    found = []

    def visit(item: Any) -> None:
        if isinstance(item, str):
            try:
                decoded = json.loads(item)
            except (ValueError, TypeError):
                return
            visit(decoded)
        elif isinstance(item, dict):
            if item.get("kind") == "identity-probe-v1":
                found.append(item)
            else:
                for child in item.values():
                    visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    # MCP can mirror the same tool result in content and structuredContent.
    unique = {json.dumps(probe, sort_keys=True): probe for probe in found}
    if len(unique) != 1:
        raise ValueError("Expected exactly one identity probe.")
    probe = next(iter(unique.values()))
    if probe.get("user_id") is not None and not isinstance(probe["user_id"], str):
        raise ValueError("The trusted identity must be an opaque string or absent.")
    return probe


def evaluate(
    pattern: str,
    configuration: str,
    baseline: str,
    observed: str | None,
    *,
    denied: bool = False,
    blocked: bool = False,
) -> Result:
    if pattern not in PATTERNS:
        raise ValueError("Unknown pattern.")
    if configuration not in ("user", "service", "drop-context"):
        raise ValueError("Unknown configuration.")
    negative = configuration != "user"
    expectation = "different-principal-or-denial" if negative else "preserve-user"
    if not baseline:
        raise ValueError("A verified direct user baseline is required.")
    if blocked:
        return Result(pattern, configuration, "BLOCKED", "prerequisite", "unavailable", expectation)
    if denied:
        return Result(pattern, configuration, "PASS" if negative else "FAIL", "authorization-denied", "denied", expectation)
    if not observed:
        return Result(pattern, configuration, "FAIL", "identity-missing", "missing", expectation)
    matches = observed == baseline
    return Result(
        pattern, configuration, "PASS" if matches != negative else "FAIL",
        "user-preserved" if matches else "identity-changed",
        "same-user" if matches else "different-principal",
        expectation,
    )
