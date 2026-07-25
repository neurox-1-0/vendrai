from app.main import app


def _parameter_names(operation: dict) -> set[str]:
    return {item["name"] for item in operation.get("parameters", [])}


def test_all_business_mutations_require_idempotency_key():
    schema = app.openapi()
    exemptions = {("put", "/api/v1/documents/{document_id}/content")}
    missing = []
    for path, item in schema["paths"].items():
        for method in {"post", "put", "patch", "delete"} & item.keys():
            if (method, path) in exemptions:
                continue
            if "Idempotency-Key" not in _parameter_names(item[method]):
                missing.append(f"{method.upper()} {path}")
    assert missing == []


def test_human_decisions_and_case_transitions_require_expected_version():
    schema = app.openapi()
    versioned = {
        ("post", "/api/v1/cases/{case_id}:submit"),
        ("post", "/api/v1/cases/{case_id}:cancel"),
        ("post", "/api/v1/cases/{case_id}:claim"),
        ("post", "/api/v1/cases/{case_id}:release"),
        ("post", "/api/v1/cases/{case_id}:retry-erp"),
        (
            "post",
            "/api/v1/approval-tasks/{task_id}/decisions",
        ),
        ("post", "/api/v1/review-tasks/{task_id}/decisions"),
        (
            "post",
            "/api/v1/clarification-tasks/{task_id}/responses",
        ),
        (
            "patch",
            "/api/v1/documents/{document_id}/fields/{field_id}",
        ),
        ("post", "/api/v1/cases/{case_id}/audit-exports"),
    }
    for method, path in versioned:
        assert "If-Match" in _parameter_names(
            schema["paths"][path][method]
        ), f"{method.upper()} {path} is missing If-Match"
