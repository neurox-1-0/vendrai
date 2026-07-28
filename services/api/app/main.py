import time
import uuid
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.observability import configure_observability
from app.routers import (
    admin,
    alerts,
    analytics,
    approvals,
    audit_exports,
    cases,
    clarifications,
    copilot,
    documents,
    evidence,
    invoices,
    knowledge,
    notifications,
    reviews,
    risk_findings,
    runs,
    work_queue,
)
from app.services.rate_limit import enforce_rate_limit

app = FastAPI(
    title="NeuroX Vendor Onboarding API",
    description="Tenant-isolated, evidence-driven vendor onboarding and human approval API.",
    version="1.0.0",
    docs_url="/docs" if settings.APP_ENV != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "If-Match", "Last-Event-ID", "X-Dev-Tenant-Id", "X-Dev-User-Id", "X-Dev-Roles"],
)

for router in (
    cases.router,
    documents.router,
    runs.router,
    approvals.router,
    reviews.router,
    work_queue.router,
    evidence.router,
    audit_exports.router,
    notifications.router,
    knowledge.router,
    clarifications.router,
    invoices.router,
    copilot.router,
    analytics.router,
    risk_findings.router,
    alerts.router,
    admin.router,
):
    app.include_router(
        router,
        prefix=settings.API_PREFIX,
        dependencies=[Depends(enforce_rate_limit)],
    )

configure_observability(app)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))[:128]
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Response-Time-Ms"] = str(round((time.perf_counter() - started) * 1000, 2))
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "data": None,
            "meta": {"request_id": request.state.request_id, "timestamp": datetime.now(UTC).isoformat()},
            "error": {"code": "VALIDATION_ERROR", "message": "Request validation failed", "details": exc.errors()},
        },
    )


@app.get("/health/live")
async def liveness():
    return {"status": "healthy"}


@app.get("/health/ready")
async def readiness():
    checks: dict[str, str] = {}
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception as exc:
        checks["database"] = f"unavailable:{type(exc).__name__}"
    return JSONResponse(
        status_code=200 if all(value == "healthy" for value in checks.values()) else 503,
        content={"status": "healthy" if all(value == "healthy" for value in checks.values()) else "degraded", "checks": checks},
    )


@app.get("/")
async def root():
    return {"service": "neurox-api", "version": app.version, "docs": app.docs_url}
