from fastapi import FastAPI
from app.config import settings

from app.routers import cases, documents

app = FastAPI(
    title="Vendor-to-Pay Multi-Agent Exception System",
    description="Core API for managing cases, documents, and agent orchestration.",
    version="0.1.0"
)

app.include_router(cases.router)
app.include_router(documents.router)

@app.get("/")
async def root():
    return {"message": "Welcome to Vendrai Vendor-to-Pay System"}

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "database": "configured" if settings.DATABASE_URL else "missing",
        "model": settings.DEFAULT_MODEL
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
