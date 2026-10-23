"""Scripted model replies for tests. Calls no model and no web search."""

import json

from pydantic import BaseModel

from app import AGENT_ROOT
from app.graph.grade import Grades, Verdict
from app.llm import EMBED_DIMENSIONS, ModelReply
from app.schemas import ClassifyResult, GenerateRequest, Ingredient, Profile, Recipe, RecipeInput, Source
from app.search import SearchFailure

EXAMPLES = AGENT_ROOT / "examples"
DISH = ClassifyResult(type="dish", normalized_name="Tomato and egg stir-fry", aliases=["Stir-fried tomato and eggs"])
NOT_FOOD = ClassifyResult(type="not_food", normalized_name=None, aliases=[])


def example_recipe() -> Recipe:
    data = json.loads((EXAMPLES / "response_succeeded.json").read_text(encoding="utf-8"))["recipe"]
    return Recipe.model_validate({**data, "warnings": []})


def with_peanuts() -> Recipe:
    recipe = example_recipe()
    recipe.ingredients.append(Ingredient(id="peanut", name="Roasted peanuts", quantity=0.25, unit="cup",
                                         origin="estimated", source_ids=[]))
    return recipe


def cites(recipe: Recipe, source_id: str) -> Recipe:
    """The recipe with every cited ingredient citing source_id instead (e.g. "k1", the knowledge-base recipe)."""
    for item in recipe.ingredients:
        if item.source_ids:
            item.source_ids = [source_id]
    return recipe


KB_HIT = {"id": "wikibooks:Stir-fried tomato and scrambled eggs", "source": "wikibooks",
          "title": "Stir-fried tomato and scrambled eggs", "title_en": "Tomato egg stir fry",
          "url": "https://en.wikibooks.org/wiki/Cookbook:Stir-fried_Tomato_and_Scrambled_Eggs", "servings": "2",
          "description": None, "cooking_method": "stir_fry", "ingredients": ["4 eggs", "2 tomatoes, cut into wedges"],
          "steps": ["Beat the eggs with salt.", "Scramble the eggs, add the tomatoes."], "notes": [],
          "@search.score": 0.83}
OTHER_HIT = {**KB_HIT, "id": "wikibooks:Egg Rice", "title": "Egg Rice", "title_en": None,
             "url": "https://en.wikibooks.org/wiki/Cookbook:Egg_Rice", "@search.score": 0.71}


class FakeSearch:
    """Stands in for app.search.AzureSearch: returns the given hits, or fails like an unreachable service."""

    def __init__(self, hits: list[dict] | None = None, fail: bool = False):
        self.hits, self.fail, self.calls = hits or [], fail, []

    def hybrid(self, text, vector, top=3, select=None, filter=None, vector_fields=("name_vector", "content_vector")):
        self.calls.append({"text": text, "top": top, "vector_fields": vector_fields, "dimensions": len(vector)})
        if self.fail:
            raise SearchFailure("SEARCH_UNAVAILABLE", "Search request failed (ConnectTimeout).")
        return self.hits


def make_request(dish="Tomato and egg stir-fry", **profile) -> GenerateRequest:
    return GenerateRequest(request_id="r1", user_id="u1", input=RecipeInput(type="dish_name", value=dish),
                           profile=Profile(**profile))


class ScriptedModelClient:
    """Returns the given recipes in order, repeating the last one. grades: the grader's answer per
    knowledge-base candidate ("same" / "variant" / "different"). prompts keeps the last user text per schema."""

    def __init__(self, classification: ClassifyResult, recipes: list[Recipe], grades: list[str] | None = None):
        self.classification = classification
        self.recipes = list(recipes)
        self.grades = grades or []
        self.calls: list[str] = []
        self.prompts: dict[str, str] = {}

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append("embed")
        return [[0.0] * EMBED_DIMENSIONS for _ in texts]

    def parse(self, role, system, user, schema: type[BaseModel]) -> ModelReply:
        self.calls.append(schema.__name__)
        self.prompts[schema.__name__] = user
        if schema is ClassifyResult:
            parsed = self.classification
        elif schema is Grades:
            parsed = Grades(verdicts=[Verdict(n=n, match=match) for n, match in enumerate(self.grades, start=1)])
        else:
            parsed = self.recipes.pop(0) if len(self.recipes) > 1 else self.recipes[0]
        return ModelReply(parsed=parsed, text=parsed.model_dump_json(), input_tokens=100, output_tokens=50)

    def search(self, role, system, user) -> ModelReply:
        self.calls.append("search")
        sources = [Source(id=f"s{n}", kind="web", title=f"Scripted source {n}", url=f"https://example.com/{n}")
                   for n in (1, 2)]
        return ModelReply(text="Scripted notes: 4 eggs, 2 tomatoes. [s1][s2]", sources=sources,
                          input_tokens=100, output_tokens=50, search_requests=1)
