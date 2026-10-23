"""Graph for LangGraph Studio. Run from agent/: langgraph dev   (setup: see README "Visualize the graph")

Same nodes and edges as the API graph, plus a first node that turns Studio's input form
(dish, servings, allergies, dislikes) into the contract's GenerateRequest. Studio can't pass a
model client in config the way the API and CLI do, so this graph builds one from agent/.env on the
first model call, and the knowledge-base search client from the same file (skipped when not set).
Only `langgraph dev` imports this file; the API and tests don't.
"""

from uuid import uuid4

from langgraph.graph import START, StateGraph
from pydantic import BaseModel, Field

from app.graph import add_recipe_nodes
from app.graph.state import State
from app.llm import AzureModelClient, ModelReply
from app.schemas import GenerateRequest, Profile, RecipeInput
from app.search import optional_search


class StudioInput(BaseModel):
    """The input form Studio shows."""

    dish: str = Field(description="Dish name, e.g. Caesar salad")
    servings: int = Field(default=2, ge=1, le=12)
    allergies: list[str] = Field(default_factory=list, description='e.g. ["peanut"]')
    dislikes: list[str] = Field(default_factory=list)


class StudioState(State, total=False):
    dish: str
    servings: int
    allergies: list[str]
    dislikes: list[str]


class EnvModelClient:
    """Creates the Azure client from agent/.env on first use, so Studio can draw the graph before any call."""

    def __init__(self):
        self._client: AzureModelClient | None = None

    def _get(self) -> AzureModelClient:
        if self._client is None:
            self._client = AzureModelClient()
        return self._client

    def parse(self, role, system, user, schema) -> ModelReply:
        return self._get().parse(role, system, user, schema)

    def search(self, role, system, user) -> ModelReply:
        return self._get().search(role, system, user)

    def embed(self, texts):
        return self._get().embed(texts)


def prepare_request(state: StudioState):
    request = GenerateRequest(
        request_id=str(uuid4()), user_id="studio",
        input=RecipeInput(type="dish_name", value=state["dish"]),
        servings=state.get("servings", 2),
        profile=Profile(allergies=state.get("allergies", []), dislikes=state.get("dislikes", [])),
    )
    return {"request": request}


builder = StateGraph(StudioState, input_schema=StudioInput)
builder.add_node("prepare_request", prepare_request)
builder.add_edge(START, "prepare_request")
add_recipe_nodes(builder, after="prepare_request")
graph = builder.compile(name="recipe_agent").with_config(
    {"configurable": {"llm": EnvModelClient(), "kb": optional_search()}})
