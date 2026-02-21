from __future__ import annotations

import os
from typing import Any

MOAT_PROMPT_TEMPLATE = """Analyze the economic moat of **[TICKER]** by evaluating its financial performance and strategic value over the last 10 years.

Provide a detailed breakdown of the following:

### 1. Quantitative Moat (Financials)
* **ROIC vs. WACC:** Has the Return on Invested Capital consistently exceeded the Cost of Capital? Quantify the average spread.
* **Margins & Pricing Power:** Analyze Gross/Operating margin stability. Can the company pass on costs to customers?
* **FCF Conversion:** Is the business model capital-light or intensive? Evaluate the FCF/Net Income ratio.

### 2. Qualitative Moat (Value & Innovation)
* **Unique Value Proposition:** What specific problem does this company solve that others cannot? What is the "switching cost" for the customer?
* **Innovation Alpha:** Evaluate the R&D efficiency. Is the company a "disruptor" or "disrupted"? Does it hold critical patents, proprietary tech, or a unique data flywheel?
* **Market Utility:** How essential is this company to its ecosystem? Does it provide a "mission-critical" service or product?

### 3. Moat Source & Verdict
* **Moat Drivers:** Identify if the moat stems from Network Effects, Intangible Assets (Brand/Patents), Switching Costs, or Cost Advantage.
* **Final Verdict:** Classify the moat as **Wide, Narrow, or None** based on both financial durability and innovation leadership."""


class LLMError(Exception):
    """Raised when the LLM request fails."""


def build_moat_prompt(ticker: str) -> str:
    normalized = ticker.strip().upper()
    return MOAT_PROMPT_TEMPLATE.replace("[TICKER]", normalized)


def _infer_provider(model: str) -> str | None:
    value = model.strip().lower()
    if not value or "/" in value:
        return None
    if value.startswith("gemini-"):
        return "gemini"
    if value.startswith("claude-"):
        return "anthropic"
    if value.startswith("gpt-") or value.startswith("o"):
        return "openai"
    if value.startswith("mistral-") or value.startswith("ministral-") or value.startswith("codestral-"):
        return "mistral"
    if value.startswith("command-"):
        return "cohere"
    if value.startswith("deepseek-"):
        return "deepseek"
    if value.startswith("grok-"):
        return "xai"
    return None


def resolve_litellm_models(model: str) -> list[str]:
    value = model.strip()
    if not value:
        return []

    if value.startswith("gemini-"):
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key and not os.getenv("GOOGLE_API_KEY"):
            os.environ["GOOGLE_API_KEY"] = gemini_key

    provider = _infer_provider(value)
    candidates = [value]
    if provider is not None:
        candidates.append(f"{provider}/{value}")

    deduped: list[str] = []
    for item in candidates:
        if item not in deduped:
            deduped.append(item)
    return deduped


def resolve_litellm_model(model: str) -> str:
    candidates = resolve_litellm_models(model)
    if not candidates:
        return model.strip()
    return candidates[-1]


def format_llm_error(model: str, error_text: str) -> str:
    lowered = error_text.lower()
    if "llm provider not provided" in lowered:
        return (
            "Provider not inferred for this model. Use /model with an explicit ID like "
            "`provider/model` (openai/gpt-5, anthropic/claude-sonnet-4-5, gemini/gemini-2.5-pro)."
        )
    if "no module named 'google.auth'" in lowered:
        return (
            "Gemini dependencies are missing (`google-auth`). "
            "Install `litellm[google]` or `google-cloud-aiplatform`, "
            "or switch model with /model."
        )
    if "google cloud sdk not found" in lowered or "default credentials" in lowered:
        return (
            "Gemini is running in Vertex mode without credentials. "
            "Set GOOGLE_API_KEY (or GEMINI_API_KEY), or configure Vertex AI credentials."
        )
    first_line = error_text.splitlines()[0].strip() if error_text.strip() else "Unknown LLM error."
    return first_line


def _flatten_exception(exc: Exception) -> str:
    parts: list[str] = []
    seen: set[int] = set()
    current: Exception | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = str(current).strip()
        if text:
            parts.append(text)
        next_exc = current.__cause__ or current.__context__
        current = next_exc if isinstance(next_exc, Exception) else None
    return "\n".join(parts)


def ask_model(model: str, system_prompt: str, user_prompt: str, timeout: int = 20) -> str:
    if model == "none":
        return ""

    resolved_models = resolve_litellm_models(model)
    if not resolved_models:
        raise LLMError("Model is empty. Set one with /model [model-name].")

    messages: list[dict[str, str]] = []
    if system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    from litellm import completion

    last_exc: Exception | None = None
    for candidate in resolved_models:
        try:
            response: Any = completion(
                model=candidate,
                messages=messages,
                timeout=timeout,
            )
            break
        except Exception as exc:  # pragma: no cover - depends on network/provider
            last_exc = exc
    else:
        assert last_exc is not None
        details = _flatten_exception(last_exc)
        raise LLMError(format_llm_error(model, details)) from last_exc

    try:
        content = response.choices[0].message.content
    except Exception as exc:
        raise LLMError(f"Invalid LLM response: {exc}") from exc

    if not content:
        raise LLMError("Empty LLM response.")

    return str(content)


def fallback_explanation(
    ticker: str,
    question: str,
    score: float,
    mos: float | None,
    criteria_lines: list[str],
) -> str:
    mos_txt = "N/A" if mos is None else f"{mos * 100:.2f}%"
    lines = [
        f"Deterministic analysis for {ticker}",
        f"Graham score: {score * 100:.1f}%",
        f"Margin of Safety: {mos_txt}",
        "Criteria:",
        *criteria_lines,
    ]
    if question:
        lines.append(f"Question: {question}")
        lines.append("Answer: use /model <name> for a richer LLM explanation.")
    return "\n".join(lines)
