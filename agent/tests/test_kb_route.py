"""Knowledge-base route (M2): kb_retrieve → grade → synthesize, and every fallback to web search."""

import json

from fakes import DISH, KB_HIT, OTHER_HIT, FakeSearch, ScriptedModelClient, cites, example_recipe, make_request

from app.graph import generate
from app.graph.grade import describe, recipe_notes
from app.llm import ModelFailure

WEB_PATH = ["classify", "kb_retrieve", "grade", "web_research", "synthesize", "validate"]


def test_same_dish_is_written_from_the_knowledge_base_without_web_search():
    llm = ScriptedModelClient(DISH, [cites(example_recipe(), "k1")], grades=["same", "different"])
    search, records = FakeSearch([KB_HIT, OTHER_HIT]), {}
    response = generate(make_request(), llm, records.__setitem__, kb=search)
    assert response.status == "succeeded" and response.error is None
    assert llm.calls == ["ClassifyResult", "embed", "Grades", "Recipe"]  # no web search
    assert search.calls == [{"text": None, "top": 3, "vector_fields": ("name_vector",), "dimensions": 512}]
    [source] = response.sources
    assert (source.id, source.kind, source.url) == ("k1", "kb", KB_HIT["url"])
    assert source.title == "Tomato egg stir fry (Wikibooks Cookbook, CC BY-SA 4.0)"  # credit Wikibooks requires
    assert '"Tomato and egg stir-fry"' in llm.prompts["Grades"]
    assert "Beat the eggs with salt." in llm.prompts["Recipe"]  # synthesize writes from the matched recipe
    assert response.usage.search_requests == 0
    assert list(response.usage.step_latency_ms) == ["classify", "kb_retrieve", "grade", "synthesize", "validate"]
    assert json.loads(records["04_grade.json"])["candidates"][1] == {"id": "wikibooks:Egg Rice", "match": "different"}


def test_only_variants_go_to_web_search():
    llm = ScriptedModelClient(DISH, [example_recipe()], grades=["variant", "different"])
    response = generate(make_request(), llm, kb=FakeSearch([KB_HIT, OTHER_HIT]))
    assert response.status == "succeeded" and "search" in llm.calls
    assert {source.kind for source in response.sources} == {"web"}
    assert list(response.usage.step_latency_ms) == WEB_PATH


def test_search_failure_falls_back_to_web_search():
    llm, records = ScriptedModelClient(DISH, [example_recipe()]), {}
    response = generate(make_request(), llm, records.__setitem__, kb=FakeSearch(fail=True))
    assert response.status == "succeeded" and "Grades" not in llm.calls and "search" in llm.calls
    assert "ConnectTimeout" in json.loads(records["03_kb_retrieve.json"])["error"]


def test_no_candidates_skip_the_grader():
    llm = ScriptedModelClient(DISH, [example_recipe()])
    response = generate(make_request(), llm, kb=FakeSearch([]))
    assert response.status == "succeeded" and "Grades" not in llm.calls
    assert list(response.usage.step_latency_ms) == ["classify", "kb_retrieve", "web_research", "synthesize", "validate"]


def test_grader_failure_falls_back_to_web_search():
    class RefusingGrader(ScriptedModelClient):
        def parse(self, role, system, user, schema):
            if schema.__name__ == "Grades":
                raise ModelFailure("MODEL_UNAVAILABLE", "The model call failed (BadRequestError, HTTP 400, content_filter).")
            return super().parse(role, system, user, schema)

    response = generate(make_request(), RefusingGrader(DISH, [example_recipe()]), kb=FakeSearch([KB_HIT]))
    assert response.status == "succeeded" and response.sources[0].kind == "web"
    assert list(response.usage.step_latency_ms) == WEB_PATH


def test_grader_sees_names_method_and_first_ingredients_only():
    hit = {**KB_HIT, "ingredients": [f"ingredient {n}" for n in range(15)], "description": "x" * 500}
    seen = describe(2, hit)
    assert seen["n"] == 2 and seen["names"] == ["Tomato egg stir fry", "Stir-fried tomato and scrambled eggs"]
    assert seen["cooking_method"] == "stir_fry" and len(seen["ingredients"]) == 10 and len(seen["description"]) == 200
    notes = recipe_notes(KB_HIT)
    assert notes.splitlines()[:3] == ["Knowledge-base recipe [k1]: Tomato egg stir fry / Stir-fried tomato and scrambled eggs",
                                      "Servings in the recipe: 2", "Ingredients:"]
    assert "2. Scramble the eggs, add the tomatoes." in notes
