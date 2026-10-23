"""Graph: classify → kb_retrieve → grade → synthesize → validate, one repair retry.

kb_retrieve looks the dish up in the recipe knowledge base (M2). When grade finds a candidate that is the
same dish, the recipe is written from it and web search is skipped; otherwise (no candidates, only
variants, knowledge base not configured or unavailable) web_research runs before synthesize, as in M1.
"""

import time
from collections.abc import Callable, Iterator
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from app.graph.classify import classify
from app.graph.grade import grade
from app.graph.kb_retrieve import kb_retrieve
from app.graph.state import State
from app.graph.synthesize import synthesize
from app.graph.validate import validate
from app.graph.web_research import web_research
from app.llm import ModelClient, ModelFailure
from app.schemas import Classification, ErrorInfo, GenerateRequest, GenerateResponse, Usage

Trace = Callable[[str, str], None]


def add_recipe_nodes(builder: StateGraph, after: str = START) -> None:
    """Adds the recipe nodes and edges, entered from `after`. Shared by the API graph and app/graph/studio.py."""
    for node in (classify, kb_retrieve, grade, web_research, synthesize, validate):
        builder.add_node(node.__name__, node)
    builder.add_edge(after, "classify")
    builder.add_conditional_edges("classify", lambda state: END if state.get("error") else "kb_retrieve",
                                  ["kb_retrieve", END])
    builder.add_conditional_edges("kb_retrieve", lambda state: "grade" if state.get("candidates") else "web_research",
                                  ["grade", "web_research"])
    builder.add_conditional_edges("grade", lambda state: "synthesize" if state.get("kb_match") else "web_research",
                                  ["synthesize", "web_research"])
    builder.add_edge("web_research", "synthesize")
    builder.add_edge("synthesize", "validate")
    builder.add_conditional_edges(
        "validate", lambda state: "synthesize" if state["problems"] and not state.get("error") else END,
        ["synthesize", END])


def build_graph():
    builder = StateGraph(State)
    add_recipe_nodes(builder)
    return builder.compile()


GRAPH = build_graph()


def new_run_id() -> str:
    return f"run_{uuid4().hex[:12]}"


def stream_generate(request: GenerateRequest, llm: ModelClient, trace: Trace | None = None,
                    kb=None) -> Iterator[tuple[str, object]]:
    """Yields ("progress", node_name) per finished node, then ("result", GenerateResponse).
    kb: the recipe search client (app.search.optional_search()); None skips the knowledge base."""
    started = time.perf_counter()
    if trace:
        trace("01_request.json", request.model_dump_json(indent=2))
    state: State = {"request": request, "usage": {}}
    step_ms: dict[str, int] = {}
    running, step_started = None, started

    def close_step():
        step_ms[running] = step_ms.get(running, 0) + round((time.perf_counter() - step_started) * 1000)

    try:
        for mode, payload in GRAPH.stream(state, {"configurable": {"llm": llm, "trace": trace, "kb": kb}},
                                          stream_mode=["tasks", "updates", "values"]):
            if mode == "values":
                state = payload
            elif mode == "tasks":
                if "input" in payload:  # a node is starting; its finish arrives as an "updates" event
                    running, step_started = payload["name"], time.perf_counter()
            else:
                for node in payload:
                    close_step()
                    running = None
                    yield "progress", node
    except ModelFailure as exc:
        if running:
            close_step()
        state = {**state, "error": ErrorInfo(code=exc.code, message=exc.message)}

    error = state.get("error")
    found = state.get("classification")
    recipe = None if error else state["recipe"]
    allergies = request.profile.allergies
    if recipe and allergies:
        recipe.warnings.append(f"Checked against your allergies: no {', '.join(allergies)} ingredients. "
                               "Always check product labels.")
    response = GenerateResponse(
        run_id=new_run_id(),
        status="succeeded" if not error else "rejected" if error.code == "NOT_A_RECIPE" else "failed",
        classification=Classification(type=found.type, normalized_name=found.normalized_name) if found else None,
        recipe=recipe,
        sources=[] if error else state["sources"],
        usage=Usage(latency_ms=round((time.perf_counter() - started) * 1000), step_latency_ms=step_ms,
                    **state.get("usage", {})),
        error=error,
    )
    if trace:
        trace("07_response.json", response.model_dump_json(indent=2))
    yield "result", response


def generate(request: GenerateRequest, llm: ModelClient, trace: Trace | None = None, kb=None) -> GenerateResponse:
    for _, payload in stream_generate(request, llm, trace, kb):
        response = payload
    return response
