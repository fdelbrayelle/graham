def command_name(line: str) -> str:
    value = line.strip()
    if not value.startswith("/"):
        return ""
    return value.split(maxsplit=1)[0].lower()


def command_start_feedback(line: str) -> str | None:
    value = line.strip()
    command = command_name(value)
    if not command:
        return None

    if command == "/moat":
        parts = value.split(maxsplit=1)
        if len(parts) == 2 and parts[1].strip():
            return f"Generating moat analysis for {parts[1].strip().upper()}..."
        return "Generating moat analysis..."

    if command == "/lang":
        return "Applying display language..."

    if command == "/indices":
        parts = value.split(maxsplit=1)
        if len(parts) == 2 and parts[1].strip():
            return f"Loading index constituents for {parts[1].strip().lower()}..."
        return "Loading supported indices..."

    return f"Running {command}..."


def command_result_feedback(line: str, response: str) -> tuple[str, str] | None:
    command = command_name(line)
    text = response.strip()
    if not command or not text:
        return None

    first_line = text.splitlines()[0]
    lowered = first_line.lower()
    if command not in {"/moat", "/lang", "/indices"}:
        return None

    severity = "information"
    if (
        "error" in lowered
        or first_line.startswith("Usage:")
        or first_line.startswith("Unknown")
        or first_line.startswith("Invalid")
    ):
        severity = "warning"
    return first_line, severity
