from datetime import date

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.observability import configure_observability
from app.retrieval import hybrid_search


class SearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    tenant_id: str
    roles: list[str]
    effective_date: str = Field(default_factory=lambda: date.today().isoformat())
    limit: int = Field(default=8, ge=4, le=8)


app = FastAPI(title="NeuroX tenant-filtered policy retrieval", docs_url=None)
configure_observability(app, service_name="neurox-retrieval-api")


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/v1/search")
async def search(body: SearchRequest):
    items = hybrid_search(body.query, body.tenant_id, body.roles, body.effective_date, body.limit)
    return {"status": "SUCCESS" if items else "INSUFFICIENT_EVIDENCE", "items": items}
