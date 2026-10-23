"""HTTP boundary for the backend. Run from agent/: python -m uvicorn app.api.main:app --port 8100"""

import hmac
import json
import os
from collections.abc import Iterator
from functools import lru_cache

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse

from app import AGENT_ROOT
from app.graph import new_run_id, stream_generate
from app.llm import AzureModelClient, ModelFailure
from app.schemas import ErrorInfo, GenerateRequest, GenerateResponse
from app.search import AzureSearch, optional_search

app = FastAPI(title="拾味 Agent Service", version="0.1.0")


def require_api_key(x_api_key: str | None = Header(default=None)):
    expected = os.getenv("AGENT_API_KEY", "")
    if not expected:
        raise HTTPException(503, "AGENT_API_KEY is not configured on the agent service.")
    if not x_api_key or not hmac.compare_digest(x_api_key.encode(), expected.encode()):
        raise HTTPException(401, "Missing or invalid X-Api-Key.")


@lru_cache
def get_llm() -> AzureModelClient:
    return AzureModelClient()


@lru_cache
def get_kb() -> AzureSearch | None:
    """Recipe knowledge base with the read-only query key; None (web search only) until it's configured."""
    return optional_search()


def mock_events() -> Iterator[tuple[str, object]]:
    """MOCK=1: the fixed example response, so the backend can integrate before any model exists."""
    for node in ("classify", "kb_retrieve", "web_research", "synthesize", "validate"):
        yield "progress", node
    response = GenerateResponse.model_validate_json(
        (AGENT_ROOT / "examples" / "response_succeeded.json").read_text(encoding="utf-8"))
    response.run_id = new_run_id()
    response.recipe.warnings.append("Mock response: fixed example; no model or web search was called.")
    yield "result", response


def run_events(body: GenerateRequest) -> Iterator[tuple[str, object]]:
    if os.getenv("MOCK") == "1":
        return mock_events()
    try:
        return stream_generate(body, get_llm(), kb=get_kb())
    except ModelFailure as exc:
        failed = GenerateResponse(run_id=new_run_id(), status="failed",
                                  error=ErrorInfo(code=exc.code, message=exc.message))
        return iter([("result", failed)])


def sse(events: Iterator[tuple[str, object]]) -> Iterator[str]:
    for event, payload in events:
        data = payload.model_dump_json() if event == "result" else json.dumps({"node": payload})
        yield f"event: {event}\ndata: {data}\n\n"


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/v1/recipes:generate", response_model=GenerateResponse, dependencies=[Depends(require_api_key)])
def generate_recipe(body: GenerateRequest, stream: bool = False):
    events = run_events(body)
    if stream:
        return StreamingResponse(sse(events), media_type="text/event-stream")
    return [payload for event, payload in events if event == "result"][0]
