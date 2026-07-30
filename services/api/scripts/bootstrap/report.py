"""The readiness report.

Every step contributes one line. The report is the deliverable as much as the
data is: an operator needs to know not only that the bootstrap ran, but which
of the things a scenario depends on are actually present.

Nothing here ever prints a password, key, or signed URL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Status = Literal["OK", "SKIPPED", "MISSING", "FAILED"]

_SYMBOLS: dict[Status, str] = {
    "OK": "OK",
    "SKIPPED": "SKIPPED",
    "MISSING": "NOT CONFIGURED",
    "FAILED": "FAILED",
}


@dataclass
class StepResult:
    label: str
    status: Status
    detail: str = ""
    # Blocks business-readiness. A step can fail without blocking (an optional
    # source), and can succeed while blocking is still required elsewhere.
    blocking: bool = True

    @property
    def is_ready(self) -> bool:
        return self.status == "OK" or not self.blocking


@dataclass
class BootstrapReport:
    steps: list[StepResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(
        self,
        label: str,
        status: Status,
        detail: str = "",
        *,
        blocking: bool = True,
    ) -> StepResult:
        result = StepResult(label=label, status=status, detail=detail, blocking=blocking)
        self.steps.append(result)
        return result

    def note(self, message: str) -> None:
        """Record an operator-facing message shown after the table.

        Used for the one thing that is not a pass/fail - an explicit,
        actionable instruction, printed instead of a stack trace.
        """
        self.notes.append(message)

    @property
    def business_ready(self) -> bool:
        return all(step.is_ready for step in self.steps)

    @property
    def blockers(self) -> list[StepResult]:
        return [step for step in self.steps if not step.is_ready]

    def render(self, *, title: str = "NeuroX bootstrap complete.") -> str:
        width = max((len(step.label) for step in self.steps), default=0)
        lines = [title, ""]
        for step in self.steps:
            detail = step.detail or _SYMBOLS[step.status]
            lines.append(f"  {step.label.ljust(width)}   {detail}")
        lines.append("")
        if self.business_ready:
            lines.append("  Business-ready:".ljust(width + 3) + "   YES")
        else:
            reasons = ", ".join(step.label.lower() for step in self.blockers)
            lines.append("  Business-ready:".ljust(width + 3) + f"   NO - {reasons}")
        for note in self.notes:
            lines.extend(["", note.rstrip()])
        return "\n".join(lines)
