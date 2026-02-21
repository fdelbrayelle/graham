import os

from graham.llm import (
    MOAT_PROMPT_TEMPLATE,
    build_moat_prompt,
    format_llm_error,
    resolve_litellm_model,
    resolve_litellm_models,
)


def test_build_moat_prompt_replaces_placeholder_with_uppercase_ticker() -> None:
    built = build_moat_prompt("msft")
    assert "[TICKER]" not in built
    assert built == MOAT_PROMPT_TEMPLATE.replace("[TICKER]", "MSFT")


def test_resolve_litellm_model_prefixes_gemini_and_maps_api_key(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "demo-key")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    resolved = resolve_litellm_model("gemini-2.5-pro")
    assert resolved == "gemini/gemini-2.5-pro"
    assert "GOOGLE_API_KEY" in os.environ


def test_resolve_litellm_models_tries_raw_then_inferred_provider() -> None:
    assert resolve_litellm_models("claude-sonnet-4-5") == [
        "claude-sonnet-4-5",
        "anthropic/claude-sonnet-4-5",
    ]
    assert resolve_litellm_models("openai/gpt-5") == ["openai/gpt-5"]


def test_format_llm_error_google_auth_missing_is_human_readable() -> None:
    message = format_llm_error("gemini-2.5-pro", "ModuleNotFoundError: No module named 'google.auth'")
    assert "google-auth" in message
    assert "Traceback" not in message


def test_format_llm_error_provider_missing_suggests_provider_model() -> None:
    message = format_llm_error(
        "my-custom-model",
        "litellm.BadRequestError: LLM Provider NOT provided. Pass in model as provider/model",
    )
    assert "provider/model" in message
