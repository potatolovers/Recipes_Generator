"""Scripted model replies for tests. Calls no model and no web search."""

import json

from pydantic import BaseModel

from app import AGENT_ROOT
from app.llm import ModelReply
from app.schemas import ClassifyResult, GenerateRequest, Ingredient, Profile, Recipe, RecipeInput, Source

EXAMPLES = AGENT_ROOT / "examples"
DISH = ClassifyResult(type="dish", normalized_name="Tomato and egg stir-fry", aliases=["番茄炒蛋"])
NOT_FOOD = ClassifyResult(type="not_food", normalized_name=None, aliases=[])


def example_recipe() -> Recipe:
    data = json.loads((EXAMPLES / "response_succeeded.json").read_text(encoding="utf-8"))["recipe"]
    return Recipe.model_validate({**data, "warnings": []})


def with_peanuts() -> Recipe:
    recipe = example_recipe()
    recipe.ingredients.append(Ingredient(id="peanut", name="Roasted peanuts", quantity=0.25, unit="cup",
                                         origin="estimated", source_ids=[]))
    return recipe


def make_request(dish="番茄炒蛋", **profile) -> GenerateRequest:
    return GenerateRequest(request_id="r1", user_id="u1", input=RecipeInput(type="dish_name", value=dish),
                           profile=Profile(**profile))


class ScriptedModelClient:
    """Returns the given recipes in order, repeating the last one."""

    def __init__(self, classification: ClassifyResult, recipes: list[Recipe]):
        self.classification = classification
        self.recipes = list(recipes)
        self.calls: list[str] = []

    def parse(self, role, system, user, schema: type[BaseModel]) -> ModelReply:
        self.calls.append(schema.__name__)
        if schema is ClassifyResult:
            parsed = self.classification
        else:
            parsed = self.recipes.pop(0) if len(self.recipes) > 1 else self.recipes[0]
        return ModelReply(parsed=parsed, text=parsed.model_dump_json(), input_tokens=100, output_tokens=50)

    def search(self, role, system, user) -> ModelReply:
        self.calls.append("search")
        sources = [Source(id=f"s{n}", kind="web", title=f"Scripted source {n}", url=f"https://example.com/{n}")
                   for n in (1, 2)]
        return ModelReply(text="Scripted notes: 4 eggs, 2 tomatoes. [s1][s2]", sources=sources,
                          input_tokens=100, output_tokens=50, search_requests=1)
