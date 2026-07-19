import asyncio
import json
from typing import TypeVar

from pydantic import BaseModel

from app.config import settings


T = TypeVar("T", bound=BaseModel)


SENSITIVE_MARKERS = ("account_number", "tax_id", "bank_account", "raw_ocr", "document_bytes")


def validate_minimized_payload(payload: dict) -> None:
    serialized = json.dumps(payload, default=str).lower()
    leaked_keys = [key for key in SENSITIVE_MARKERS if key in serialized]
    if leaked_keys:
        raise ValueError(f"LLM payload rejected by data minimization policy: {', '.join(leaked_keys)}")


async def structured_reasoning(prompt: str, payload: dict, response_model: type[T]) -> T:
    """Provider gateway; external calls are disabled unless explicitly allowed."""
    validate_minimized_payload(payload)
    if not settings.ALLOW_EXTERNAL_LLM or not settings.GEMINI_API_KEY:
        raise RuntimeError("EXTERNAL_LLM_DISABLED")
    from langchain_google_genai import ChatGoogleGenerativeAI
    llm = ChatGoogleGenerativeAI(
        model=settings.DEFAULT_MODEL,
        google_api_key=settings.GEMINI_API_KEY,
        temperature=0,
        timeout=20,
        max_retries=0,
    ).with_structured_output(response_model)
    return await asyncio.wait_for(llm.ainvoke([("system", prompt), ("user", json.dumps(payload))]), timeout=25)
