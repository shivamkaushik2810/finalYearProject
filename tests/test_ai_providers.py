import json

import httpx

from src.analytics import ai_insights as ai
from test_ai_insights import payload, card


def _secrets(monkeypatch, **kw):
    monkeypatch.setattr(ai, "_secret", lambda name, default=None: kw.get(name, default))


def test_groq_preset_is_used(monkeypatch):
    _secrets(monkeypatch, GROQ_API_KEY="k")
    seen = {}

    def fake(base, key, model, prompt):
        seen.update(base=base, key=key, model=model)
        return json.dumps([card()])

    monkeypatch.setattr(ai, "_openai_compat_generate", fake)
    out = ai.interpret(payload())
    assert out["status"] == "ok" and seen["base"] == "https://api.groq.com/openai/v1" and seen["key"] == "k"
    assert out["model"] == seen["model"]


def test_generic_provider_overrides(monkeypatch):
    _secrets(monkeypatch, AI_PROVIDER="openai_compatible", AI_API_KEY="k", AI_BASE_URL="http://x/v1", AI_MODEL="m")
    seen = {}
    monkeypatch.setattr(ai, "_openai_compat_generate",
                        lambda base, key, model, prompt: (seen.update(base=base, model=model), json.dumps([card()]))[1])
    assert ai.interpret(payload())["status"] == "ok" and seen == {"base": "http://x/v1", "model": "m"}


def test_openrouter_without_a_model_is_unavailable(monkeypatch):
    _secrets(monkeypatch, AI_PROVIDER="openrouter", OPENROUTER_API_KEY="k")
    assert ai.interpret(payload())["status"] == "unavailable"


def test_ollama_needs_no_key(monkeypatch):
    _secrets(monkeypatch, AI_PROVIDER="ollama")
    monkeypatch.setattr(ai, "_openai_compat_generate", lambda base, key, model, prompt: json.dumps([card()]))
    assert ai.interpret(payload())["status"] == "ok"


def test_rate_limit_gives_friendly_message(monkeypatch):
    _secrets(monkeypatch, GROQ_API_KEY="k")

    def boom(base, key, model, prompt):
        raise httpx.HTTPStatusError("429", request=httpx.Request("POST", "http://x"), response=httpx.Response(429))

    monkeypatch.setattr(ai, "_openai_compat_generate", boom)
    out = ai.interpret(payload())
    assert out["status"] == "error" and "quota" in out["message"]


def test_provider_autodetected_from_keys(monkeypatch):
    _secrets(monkeypatch, OPENROUTER_API_KEY="k")
    assert ai._pick_provider() == "openrouter"
    _secrets(monkeypatch)
    assert ai._pick_provider() is None
