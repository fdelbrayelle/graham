from __future__ import annotations

from typing import Any

from litellm import completion


class LLMError(Exception):
    """Raised when the LLM request fails."""


def ask_model(model: str, system_prompt: str, user_prompt: str, timeout: int = 20) -> str:
    if model == "none":
        return ""

    try:
        response: Any = completion(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            timeout=timeout,
        )
    except Exception as exc:  # pragma: no cover - depends on network/provider
        raise LLMError(str(exc)) from exc

    try:
        content = response.choices[0].message.content
    except Exception as exc:
        raise LLMError(f"Reponse LLM invalide: {exc}") from exc

    if not content:
        raise LLMError("Reponse LLM vide.")

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
        f"Analyse deterministe {ticker}",
        f"Score Graham: {score * 100:.1f}%",
        f"Margin of Safety: {mos_txt}",
        "Criteres:",
        *criteria_lines,
    ]
    if question:
        lines.append(f"Question: {question}")
        lines.append("Reponse: utilisez /model <nom> pour une explication LLM plus riche.")
    return "\n".join(lines)
