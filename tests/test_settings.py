from pathlib import Path

from graham.settings import load_persisted_language


def test_load_persisted_language_reads_config_value(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("graham.settings.Path.home", lambda: tmp_path)
    config_path = tmp_path / ".graham" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text('{"default_language":"fr"}', encoding="utf-8")
    assert load_persisted_language("en") == "fr"


def test_load_persisted_language_falls_back_to_default_when_missing(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("graham.settings.Path.home", lambda: tmp_path)
    assert load_persisted_language("de") == "de"


def test_load_persisted_language_normalizes_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("graham.settings.Path.home", lambda: tmp_path)
    assert load_persisted_language(" FR ") == "fr"
