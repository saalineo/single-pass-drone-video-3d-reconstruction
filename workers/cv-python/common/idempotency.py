import hashlib


def stage_input_hash(*parts: str) -> str:
    h = hashlib.sha256()
    for p in sorted(parts):
        h.update(p.encode("utf-8"))
    return h.hexdigest()


def short_id(full_hash: str) -> str:
    return full_hash[:16]
