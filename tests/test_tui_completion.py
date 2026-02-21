from graham.completion import apply_completion
from graham.search import matches_ticker_or_company_query


def test_apply_completion_keeps_command_when_prompt_ends_with_space() -> None:
    assert apply_completion("/moat ", "MSFT") == "/moat MSFT"


def test_apply_completion_replaces_current_argument_fragment() -> None:
    assert apply_completion("/lang e", "en") == "/lang en"


def test_apply_completion_keeps_lang_command_when_prompt_ends_with_space() -> None:
    assert apply_completion("/lang ", "fr") == "/lang fr"


def test_ticker_search_filters_on_ticker() -> None:
    assert matches_ticker_or_company_query("MC.PA", "LVMH", "MC")
    assert not matches_ticker_or_company_query("AI.PA", "Air Liquide", "MC")


def test_ticker_search_filters_on_company_name() -> None:
    assert matches_ticker_or_company_query("AI.PA", "Air Liquide", "LIQUIDE")
    assert not matches_ticker_or_company_query("MC.PA", "LVMH", "LIQUIDE")
