import hashlib


def stage_input_hash(*parts: str) -> str:
    return hashlib.sha256("".join(sorted(parts)).encode("utf-8")).hexdigest()


def short_id(full_hash: str) -> str:
    return full_hash[:16]
