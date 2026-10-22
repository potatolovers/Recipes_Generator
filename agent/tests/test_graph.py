import time

from fakes import DISH, NOT_FOOD, ScriptedModelClient, example_recipe, make_request, with_peanuts

from app.graph import generate, stream_generate
from app.llm import ModelFailure
from app.schemas import GenerateResponse


def test_success_is_schema_valid_and_records_trace():
    records = {}
    response = generate(make_request(), ScriptedModelClient(DISH, [example_recipe()]), records.__setitem__)
    assert response.status == "succeeded" and response.error is None
    assert GenerateResponse.model_validate_json(response.model_dump_json()) == response
    assert response.classification.model_dump() == {"type": "dish", "normalized_name": "Tomato and egg stir-fry"}
    assert response.recipe.ingredients[0].source_ids == ["s1", "s2"]
    assert response.usage.search_requests == 1 and response.usage.input_tokens == 300
    assert list(response.usage.step_latency_ms) == ["classify", "web_research", "synthesize", "validate"]
    assert list(records) == ["01_request.json", "02_classify.json", "03_research.json",
                             "04_synthesize_1.json", "05_response.json"]


def test_progress_events_follow_node_order():
    events = list(stream_generate(make_request(), ScriptedModelClient(DISH, [example_recipe()])))
    assert [payload for event, payload in events if event == "progress"] == [
        "classify", "web_research", "synthesize", "validate"]
    assert events[-1][0] == "result"


def test_non_food_is_rejected_without_search():
    llm = ScriptedModelClient(NOT_FOOD, [example_recipe()])
    response = generate(make_request("how do I fix my car"), llm)
    assert response.status == "rejected" and response.error.code == "NOT_A_RECIPE"
    assert response.recipe is None and llm.calls == ["ClassifyResult"]
    assert response.usage.search_requests == 0 and list(response.usage.step_latency_ms) == ["classify"]


def test_allergen_draft_is_repaired_once():
    llm = ScriptedModelClient(DISH, [with_peanuts(), example_recipe()])
    response = generate(make_request("宫保鸡丁", allergies=["peanut"]), llm)
    assert response.status == "succeeded" and llm.calls.count("Recipe") == 2
    assert response.recipe.warnings[-1].startswith("Checked against your allergies: no peanut ingredients.")


def test_retry_cap_fails_instead_of_returning_allergen():
    llm = ScriptedModelClient(DISH, [with_peanuts()])
    response = generate(make_request("宫保鸡丁", allergies=["Peanut"]), llm)
    assert response.status == "failed" and response.error.code == "VALIDATION_FAILED"
    assert response.recipe is None and llm.calls.count("Recipe") == 2


def test_wrong_servings_and_unknown_source_fail_validation():
    recipe = example_recipe()
    recipe.servings = 4
    recipe.ingredients[0].source_ids = ["s9"]
    response = generate(make_request(), ScriptedModelClient(DISH, [recipe]))
    assert response.status == "failed"
    assert "servings must be 2" in response.error.message and "unknown source id" in response.error.message


def test_model_failure_becomes_failed_response():
    class Broken(ScriptedModelClient):
        def search(self, role, system, user):
            time.sleep(0.05)
            raise ModelFailure("MODEL_TIMEOUT", "The model request timed out.")

    response = generate(make_request(), Broken(DISH, [example_recipe()]))
    assert response.status == "failed" and response.error.code == "MODEL_TIMEOUT"
    assert response.classification.type == "dish" and response.recipe is None
    assert list(response.usage.step_latency_ms) == ["classify", "web_research"]
    assert response.usage.step_latency_ms["web_research"] >= 40  # slept 50 ms; Windows timers run a little short


def test_step_latency_sums_repeated_nodes():
    class Slow(ScriptedModelClient):
        def parse(self, role, system, user, schema):
            time.sleep(0.03)
            return super().parse(role, system, user, schema)

    response = generate(make_request(allergies=["peanut"]), Slow(DISH, [with_peanuts(), example_recipe()]))
    steps = response.usage.step_latency_ms
    # synthesize ran twice (2 x 30 ms sleep); thresholds leave room for timer jitter and rounding.
    assert steps["synthesize"] >= 40 and steps["synthesize"] > steps["classify"] >= 15 and steps["validate"] < 15
    assert sum(steps.values()) <= response.usage.latency_ms + len(steps)
