from typing import Annotated, TypedDict

from langchain_core.runnables import RunnableConfig

from app.llm import ModelClient, ModelReply
from app.schemas import ClassifyResult, ErrorInfo, GenerateRequest, Recipe, Source


def add_usage(total: dict[str, int], delta: dict[str, int]) -> dict[str, int]:
    return {key: total.get(key, 0) + delta.get(key, 0) for key in {*total, *delta}}


class State(TypedDict, total=False):
    request: GenerateRequest
    classification: ClassifyResult
    candidates: list[dict]  # knowledge-base hits for the dish name, best first (kb_retrieve)
    kb_match: str  # id of the candidate graded the same dish; the recipe is then written from it alone
    notes: str
    sources: list[Source]
    recipe: Recipe
    problems: list[str]
    attempts: int
    usage: Annotated[dict[str, int], add_usage]
    error: ErrorInfo


def llm_of(config: RunnableConfig) -> ModelClient:
    return config["configurable"]["llm"]


def kb_of(config: RunnableConfig):
    """The recipe search client (app.search.AzureSearch), or None when the knowledge base isn't configured."""
    return config["configurable"].get("kb")


def record(config: RunnableConfig, name: str, value: str) -> None:
    trace = config["configurable"].get("trace")
    if trace:
        trace(name, value)


def usage_of(reply: ModelReply) -> dict[str, int]:
    return {"input_tokens": reply.input_tokens, "output_tokens": reply.output_tokens,
            "search_requests": reply.search_requests}
