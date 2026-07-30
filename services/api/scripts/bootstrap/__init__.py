"""Clean-install bootstrap: take a healthy stack to business-ready.

A stack where every container is green can still fail every business scenario,
because the data those scenarios depend on - the vendor master, invoice
history, policies, and sanctions lists - is never loaded. The consequence is
subtle and dangerous: scenarios fail for the wrong reason, or "pass" by finding
nothing in an empty table, and a casual observer sees a working system.

This package closes that gap with one idempotent command.

**Design rule: bootstrap through public interfaces.** Policies are published
through the product's own knowledge API rather than by writing ORM rows, so
each run exercises authorization, idempotency, audit logging, event emission,
and indexing. That makes the bootstrap the product's first integration test as
well as its data load.

Two deliberate exceptions, where no public interface exists and none should be
invented: reference data (an external system of record, not user-created
content) and the tenant and users themselves (chicken-and-egg with auth).

See plans/02-phase-1-bootstrap.md.
"""

from scripts.bootstrap.report import BootstrapReport, StepResult

__all__ = ["BootstrapReport", "StepResult"]
