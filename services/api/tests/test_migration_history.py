"""Regression checks for the immutable Alembic history."""

import ast
from pathlib import Path

VERSIONS_DIR = Path(__file__).parents[1] / "alembic" / "versions"


def test_historical_migrations_do_not_create_current_metadata() -> None:
    """Each revision must create only the schema objects it owns.

    Calling ``Base.metadata.create_all`` from an old revision makes a fresh
    database depend on today's ORM models. A later revision then attempts to
    create the same tables and the migration chain fails with DuplicateTable.
    """

    violations: list[str] = []
    for migration in sorted(VERSIONS_DIR.glob("*.py")):
        tree = ast.parse(migration.read_text(), filename=str(migration))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"create_all", "drop_all"}
            ):
                violations.append(f"{migration.name}:{node.lineno}")

    assert violations == [], (
        "Historical migrations must use explicit Alembic operations, not "
        f"mutable ORM metadata: {', '.join(violations)}"
    )
