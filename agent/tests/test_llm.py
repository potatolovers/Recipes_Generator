"""The deployment behind each model role in AzureModelClient.models. No network."""

import pytest

from app.llm import AzureModelClient, ModelFailure


@pytest.fixture
def azure(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://agent-learn-resource.openai.azure.com/openai/v1")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "dummy")
    monkeypatch.setenv("AGENT_MODEL_CLASSIFY", "gpt-4o")
    monkeypatch.setenv("AGENT_MODEL_MAIN", "gpt-4o")
    monkeypatch.delenv("AGENT_MODEL_LIGHTWEIGHT", raising=False)
    return monkeypatch


def test_lightweight_uses_its_own_deployment(azure):
    azure.setenv("AGENT_MODEL_LIGHTWEIGHT", "gpt-4.1-mini")
    assert AzureModelClient().models == {"classify": "gpt-4o", "main": "gpt-4o", "lightweight": "gpt-4.1-mini"}


def test_lightweight_falls_back_to_classify(azure):
    assert AzureModelClient().models["lightweight"] == "gpt-4o"


def test_main_model_is_required(azure):
    azure.delenv("AGENT_MODEL_MAIN")
    with pytest.raises(ModelFailure, match="AGENT_MODEL_MAIN"):
        AzureModelClient()
