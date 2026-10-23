import json

import pytest
from fakes import DISH, EXAMPLES, ScriptedModelClient, example_recipe, make_request
from fastapi.testclient import TestClient

from app.api import main
from app.graph.validate import check_recipe
from app.llm import ModelFailure
from app.schemas import GenerateRequest, GenerateResponse, Profile
from evals.run_eval import CASES, label, score

URL = "/v1/recipes:generate"
KEY = {"X-Api-Key": "test-key"}
BODY = json.loads((EXAMPLES / "request.json").read_text(encoding="utf-8"))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AGENT_API_KEY", "test-key")
    monkeypatch.setenv("MOCK", "1")
    return TestClient(main.app)


def test_examples_match_the_contract():
    request = GenerateRequest.model_validate(BODY)
    for name in ("succeeded", "rejected", "failed"):
        response = GenerateResponse.model_validate_json((EXAMPLES / f"response_{name}.json").read_text("utf-8"))
        assert response.status == name
    succeeded = GenerateResponse.model_validate_json((EXAMPLES / "response_succeeded.json").read_text("utf-8"))
    assert check_recipe(succeeded.recipe, request, succeeded.sources) == []


def test_healthz_needs_no_key(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_api_key_is_required(client, monkeypatch):
    assert client.post(URL, json=BODY).status_code == 401
    assert client.post(URL, json=BODY, headers={"X-Api-Key": "wrong"}).status_code == 401
    monkeypatch.delenv("AGENT_API_KEY")
    assert client.post(URL, json=BODY, headers=KEY).status_code == 503


def test_mock_mode_returns_marked_example(client):
    response = client.post(URL, json=BODY, headers=KEY)
    assert response.status_code == 200
    parsed = GenerateResponse.model_validate(response.json())
    assert parsed.status == "succeeded" and parsed.run_id != "run_01JB7Q"
    assert parsed.recipe.warnings[-1].startswith("Mock response")


def test_stream_sends_progress_then_result(client):
    text = client.post(URL, params={"stream": "true"}, json=BODY, headers=KEY).text
    events = [block.split("\n")[0] for block in text.strip().split("\n\n")]
    assert events == ["event: progress"] * 5 + ["event: result"]
    assert GenerateResponse.model_validate_json(text.strip().split("data: ")[-1]).status == "succeeded"


def test_bad_request_is_rejected_by_schema(client):
    assert client.post(URL, json={**BODY, "servings": 0}, headers=KEY).status_code == 422


def test_real_mode_runs_the_graph(client, monkeypatch):
    monkeypatch.setenv("MOCK", "0")
    monkeypatch.setattr(main, "get_llm", lambda: ScriptedModelClient(DISH, [example_recipe()]))
    monkeypatch.setattr(main, "get_kb", lambda: None)  # never the real search service from .env
    parsed = GenerateResponse.model_validate(client.post(URL, json=BODY, headers=KEY).json())
    assert parsed.status == "succeeded" and parsed.sources[0].id == "s1"


def test_missing_model_config_is_a_failed_response(client, monkeypatch):
    def broken():
        raise ModelFailure("MODEL_CONFIG", "not configured")

    monkeypatch.setenv("MOCK", "0")
    monkeypatch.setattr(main, "get_llm", broken)
    parsed = GenerateResponse.model_validate(client.post(URL, json=BODY, headers=KEY).json())
    assert parsed.status == "failed" and parsed.error.code == "MODEL_CONFIG"


def test_eval_cases_and_scoring():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    assert sum("must_have" in case and "profile" not in case for case in cases) == 20
    profiled = [case for case in cases if "profile" in case]
    assert len(profiled) == 8 and all(case["must_not_have"] for case in profiled)
    for case in profiled:
        Profile(**case["profile"])
    assert label(profiled[1]) == "Pad thai [allergies=peanut,shellfish; dislikes=cilantro]"
    succeeded = GenerateResponse.model_validate_json((EXAMPLES / "response_succeeded.json").read_text("utf-8"))
    assert score(cases[0], succeeded) == []
    assert score({"dish": "x", "must_have": [["tofu"]]}, succeeded) == ["missing ingredient: tofu"]
    assert score({"dish": "x", "must_not_have": ["tomato", "peanut"]}, succeeded) == ["unwanted ingredient: tomato"]
    assert score({"dish": "x", "expect": "rejected"}, succeeded)[0].startswith("status succeeded")
    assert make_request().servings == 2
