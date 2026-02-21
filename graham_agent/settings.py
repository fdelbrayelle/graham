from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class UserSettings:
    score_green_min: float = 0.80
    score_orange_min: float = 0.60
    default_universe: str = "sample"
    default_language: str = "en"


def settings_path() -> Path:
    return Path.home() / ".graham" / "config.json"


def load_user_settings() -> UserSettings:
    path = settings_path()
    if not path.exists():
        return UserSettings()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return UserSettings()

    settings = UserSettings()
    settings.score_green_min = _safe_ratio(payload.get("score_green_min"), settings.score_green_min)
    settings.score_orange_min = _safe_ratio(payload.get("score_orange_min"), settings.score_orange_min)
    if settings.score_orange_min > settings.score_green_min:
        settings.score_orange_min = min(settings.score_green_min, 0.60)

    default_universe = payload.get("default_universe")
    if isinstance(default_universe, str) and default_universe.strip():
        settings.default_universe = default_universe.strip()

    default_language = payload.get("default_language")
    if isinstance(default_language, str) and default_language.strip():
        settings.default_language = default_language.strip().lower()
    return settings


def save_user_settings(settings: UserSettings) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")


def _safe_ratio(value: object, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default

    if number > 1:
        number = number / 100.0
    if number < 0:
        return 0.0
    if number > 1:
        return 1.0
    return number
