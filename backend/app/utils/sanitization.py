def compact_log_value(value: str, limit: int = 120) -> str:
    text = " ".join(str(value).split())
    return text[:limit]
