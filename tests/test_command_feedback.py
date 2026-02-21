from graham.command_feedback import command_result_feedback, command_start_feedback


def test_start_feedback_for_moat_uses_uppercase_symbol() -> None:
    assert command_start_feedback("/moat ai.pa") == "Generating moat analysis for AI.PA..."


def test_start_feedback_for_lang() -> None:
    assert command_start_feedback("/lang fr") == "Applying display language..."


def test_start_feedback_for_indices() -> None:
    assert command_start_feedback("/indices msci_world") == "Loading index constituents for msci_world..."


def test_start_feedback_for_generic_command() -> None:
    assert command_start_feedback("/scan --top 5") == "Running /scan..."


def test_start_feedback_for_unknown_slash_command() -> None:
    assert command_start_feedback("/foobar test") == "Running /foobar..."


def test_result_feedback_for_lang_success() -> None:
    assert command_result_feedback("/lang fr", "Display language set to: fr") == (
        "Display language set to: fr",
        "information",
    )


def test_result_feedback_for_moat_error_is_warning() -> None:
    assert command_result_feedback("/moat AI.PA", "LLM error while generating moat analysis.") == (
        "LLM error while generating moat analysis.",
        "warning",
    )


def test_result_feedback_for_indices_success() -> None:
    assert command_result_feedback("/indices sp500", "Index loaded: sp500 (503 tickers).") == (
        "Index loaded: sp500 (503 tickers).",
        "information",
    )


def test_result_feedback_ignored_for_other_commands() -> None:
    assert command_result_feedback("/scan --top 5", "Scan completed: 5 results") is None
