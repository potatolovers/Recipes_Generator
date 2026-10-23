"""Backend ↔ agent contract v0 (docs/AGENT_SERVICE_PLAN.md). JSON uses snake_case.

Recipe and ClassifyResult double as strict structured-output schemas, so they carry no
numeric constraints; graph/validate.py checks the values in code.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "0.1"

Origin = Literal["extracted", "estimated"]
Unit = Literal["count", "pinch", "tsp", "tbsp", "cup", "fl_oz", "oz", "lb", "to_taste"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --- request (backend → agent) ---

class RecipeInput(Contract):
    type: Literal["dish_name"]
    value: str = Field(min_length=1, max_length=200)


class Profile(Contract):
    allergies: list[str] = Field(default_factory=list)
    diet: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)


class GenerateRequest(Contract):
    schema_version: Literal["0.1"] = SCHEMA_VERSION
    request_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    input: RecipeInput
    servings: int = Field(default=2, ge=1, le=12)
    profile: Profile = Field(default_factory=Profile)
    locale: str = "en-US"


# --- response (agent → backend) ---

class Classification(Contract):
    type: Literal["dish", "not_food"]
    normalized_name: str | None


class ClassifyResult(Classification):
    """What the classify node asks the model for; aliases stay inside the graph."""

    aliases: list[str]


class Times(Contract):
    prep_min: int
    cook_min: int
    total_min: int
    origin: Origin


class Ingredient(Contract):
    id: str
    name: str
    quantity: float | None
    unit: Unit
    prep: str | None = None
    origin: Origin
    source_ids: list[str]


class StepIngredient(Contract):
    ingredient_id: str
    quantity: float | None
    unit: Unit


class Step(Contract):
    order: int
    instruction: str
    ingredients_used: list[StepIngredient]
    duration_min: float | None = None
    tip: str | None = None


class Recipe(Contract):
    title: str
    servings: int
    times: Times
    ingredients: list[Ingredient]
    steps: list[Step]
    warnings: list[str]


class Source(Contract):
    id: str
    kind: Literal["web", "kb"]  # kb: a recipe from the agent's knowledge base (url = its original page)
    title: str
    url: str


class Usage(Contract):
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    search_requests: int = 0
    # Node name → milliseconds, summed when a node runs twice (repair retry). Includes a node that failed.
    step_latency_ms: dict[str, int] = Field(default_factory=dict)


class ErrorInfo(Contract):
    code: str
    message: str = ""


class GenerateResponse(Contract):
    schema_version: Literal["0.1"] = SCHEMA_VERSION
    run_id: str
    status: Literal["succeeded", "rejected", "failed"]
    classification: Classification | None = None
    recipe: Recipe | None = None
    sources: list[Source] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    error: ErrorInfo | None = None
