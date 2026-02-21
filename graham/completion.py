def apply_completion(current: str, selected: str) -> str:
    trimmed = current.rstrip()
    if not trimmed:
        return selected
    if current.endswith(" "):
        return f"{trimmed} {selected}"
    if " " in trimmed:
        head, _, _ = trimmed.rpartition(" ")
        return f"{head} {selected}" if head else selected
    return selected
