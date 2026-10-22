"""Cooking-method list, labeling (kb.methods), merging (kb.build) and index fields, with scripted fakes."""

import io
import json
import re

import httpx
import pytest
from pydantic import ValidationError

from kb.cooking import FAMILIES, METHOD_CODES, METHODS, prompt_table
from app.llm import ModelReply
from app.search import AzureSearch
from kb import methods, upload
from kb.build import apply_methods
from kb.sources.record import KBRecipe

ANSWERS = {  # title -> (main, all) the scripted model gives
    "红烧排骨": ("red_braise", ["blanch", "red_braise", "red_braise"]),
    "Beef Stew I": ("stew", ["sear", "simmer"]),  # main missing from all
    "Layer Cake": ("bake", ["whip", "bake", "chill_set", "caramelize", "freeze", "toast"]),  # too many
}


class RateLimited(Exception):
    pass


class ScriptedModel:
    def __init__(self, fail_first: int = 0):
        self.calls, self.fail_first, self.roles = 0, fail_first, []

    def parse(self, role, system, user, schema):
        self.calls += 1
        self.roles.append(role)
        if self.calls <= self.fail_first:
            raise RateLimited("429")
        items = []
        for line in user.splitlines():
            number, rest = line.split(". ", 1)
            main, all_ = ANSWERS[rest.split(" | ")[0]]
            items.append(methods.MethodAnswer(n=int(number), main=main, all=all_))
        items.append(methods.MethodAnswer(n=99, main="boil", all=["boil"]))  # out of range: ignored
        return ModelReply(parsed=methods.MethodBatch(items=items), input_tokens=1000, output_tokens=100)


def recipe(id_: str, title: str, source: str = "wikibooks") -> dict:
    return {"id": id_, "title": title, "source": source, "cuisine": None, "category": None,
            "ingredients": ["a"], "steps": ["Brown the meat.", "Simmer 2 hours."]}


def test_method_list_is_consistent():
    assert len(METHODS) >= 70 and len(set(METHOD_CODES)) == len(METHOD_CODES)
    assert all(re.fullmatch(r"[a-z_]+", m.code) and m.zh and m.en and m.family in FAMILIES for m in METHODS)
    table = prompt_table()
    assert all(f"{code} = " in table for code in METHOD_CODES)
    assert {m.family for m in METHODS} == set(FAMILIES)


def test_answers_outside_the_list_are_rejected():
    with pytest.raises(ValidationError):
        methods.MethodAnswer(n=1, main="fry_it", all=[])


def test_entry_keeps_main_in_all_dedupes_and_caps():
    batch = [recipe("w:1", "Beef Stew I"), recipe("h:1", "红烧排骨"), recipe("w:2", "Layer Cake")]
    got = {e["title"]: e for e in (methods.entry(r, methods.MethodAnswer(n=1, main=ANSWERS[r["title"]][0],
                                                                          all=ANSWERS[r["title"]][1])) for r in batch)}
    assert got["Beef Stew I"]["all"] == ["stew", "sear", "simmer"]
    assert got["红烧排骨"]["all"] == ["blanch", "red_braise"]
    assert got["Layer Cake"]["all"] == ["whip", "bake", "chill_set", "caramelize", "freeze"]


def test_steps_keep_start_and_end_when_shortened():
    text = methods.shorten("A" * 400 + "B" * 400, limit=600)
    assert text.startswith("A" * 300) and text.endswith("B" * 300) and " … " in text


def test_label_saves_answers_resumes_and_redoes(monkeypatch):
    monkeypatch.setattr(methods, "RETRY_PAUSES", (0,))
    recipes = [recipe("w:1", "Beef Stew I"), recipe("h:1", "红烧排骨", source="howtocook")]
    out, model = io.StringIO(), ScriptedModel(fail_first=1)
    stats = methods.label(model, recipes, {}, out, RateLimited, workers=1, price=(2.5, 10))
    saved = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [e["id"] for e in saved] == ["h:1", "w:1"]  # HowToCook first; n=99 ignored
    assert set(model.roles) == {"lightweight"} and stats["labeled"] == 2
    assert methods.estimate_cost(stats, (2.5, 10)) == ", ~$0.00"

    again = ScriptedModel()
    methods.label(again, recipes, {e["id"]: e for e in saved}, io.StringIO(), RateLimited, workers=1)
    assert again.calls == 0  # nothing left to ask
    methods.label(again, recipes, {e["id"]: e for e in saved}, io.StringIO(), RateLimited, workers=1, redo=True)
    assert again.calls == 1


class Refused(Exception):
    pass


class FilteredModel(ScriptedModel):
    """Like Azure's content filter: refuses any prompt that contains a blocked title."""

    def parse(self, role, system, user, schema):
        if "Mutura" in user:
            self.calls += 1
            raise Refused("The model call failed (BadRequestError, HTTP 400, content_filter).")
        return super().parse(role, system, user, schema)


def test_refused_batch_is_split_until_the_refused_recipe_is_alone(monkeypatch):
    monkeypatch.setattr(methods, "RETRY_PAUSES", (60,))  # a refusal must not wait or retry
    monkeypatch.setattr(methods.time, "sleep", lambda seconds: pytest.fail("slept after a refusal"))
    ANSWERS["Mutura"] = ("grill", ["boil", "grill"])
    titles = ["Beef Stew I", "红烧排骨", "Mutura", "Layer Cake"]
    recipes = [recipe(f"w:{n}", title) for n, title in enumerate(titles)]
    out, model = io.StringIO(), FilteredModel()
    stats = methods.label(model, recipes, {}, out, Refused, workers=1)
    saved = [json.loads(line)["title"] for line in out.getvalue().splitlines()]
    assert saved == ["Beef Stew I", "红烧排骨", "Layer Cake"] and stats["refused"] == ["Mutura"]
    assert stats["failed"] == 0 and model.calls == 5  # all 4 refused; [0, 1] answered; [2, 3] refused; [2] refused; [3] answered
    del ANSWERS["Mutura"]


def test_build_merges_methods_and_family():
    dish = KBRecipe(id="h:1", source="howtocook", title="红烧排骨", language="zh", url="", license="",
                    ingredients=["a"], steps=["s"])
    assert apply_methods(dish, {"id": "h:1", "title": "红烧排骨", "main": "red_braise", "all": ["blanch", "red_braise", "not_a_code"]})
    assert (dish.cooking_method, dish.cooking_methods, dish.cooking_family) == ("red_braise", ["blanch", "red_braise"], "braise_stew")
    assert not apply_methods(dish, {"id": "h:1", "title": "renamed", "main": "stew", "all": []})
    assert not apply_methods(dish, {"id": "h:1", "title": "红烧排骨", "main": "not_a_code", "all": []})


def test_index_has_filterable_method_fields_and_query_can_filter(monkeypatch):
    fields = {spec["name"]: spec for spec in upload.INDEX["fields"]}
    for name in ("cooking_method", "cooking_methods", "cooking_family"):
        assert fields[name]["filterable"] and fields[name]["facetable"] and not fields[name]["searchable"]
    doc = upload.document({**recipe("h:1", "红烧排骨"), "cooking_method": "red_braise",
                           "cooking_methods": ["blanch", "red_braise"], "cooking_family": "braise_stew"}, [0.0] * 512, [0.0] * 512)
    assert (doc["cooking_method"], doc["cooking_methods"], doc["cooking_family"]) == ("red_braise", ["blanch", "red_braise"], "braise_stew")
    assert set(doc) <= set(fields)

    bodies = []
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://shiwei-search.search.windows.net")
    monkeypatch.setenv("AZURE_SEARCH_QUERY_KEY", "query-key")
    transport = httpx.MockTransport(lambda request: bodies.append(json.loads(request.content)) or httpx.Response(200, json={"value": []}))
    AzureSearch(http=httpx.Client(transport=transport)).hybrid("beef", [0.1] * 512, filter="cooking_method eq 'stew'")
    assert bodies[0]["filter"] == "cooking_method eq 'stew'"
