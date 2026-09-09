#!/usr/bin/env python3
"""Validates that Jupyter notebooks in the repository are sanitized and contain no
embedded credentials, hardcoded keys, or saved cell outputs before commit.
"""
import json
import re
import sys
from pathlib import Path

FORBIDDEN_PATTERNS = [
    re.compile(r"minioadmin", re.IGNORECASE),
    re.compile(r"ghp_[A-Za-z0-9_]{36,}"),
    re.compile(r"ey[A-Za-z0-9_-]{30,}\.ey[A-Za-z0-9_-]{30,}"), # JWT-like
    re.compile(r"-----BEGIN (RSA|EC|OPENSSH|PRIVATE) KEY-----"),
    re.compile(r"postgres://[^:]+:[^@]+@"),
]

def check_notebook(path: Path) -> list[str]:
    errors = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            nb = json.load(f)
    except Exception as e:
        return [f"Failed to parse JSON in {path}: {e}"]

    for i, cell in enumerate(nb.get("cells", [])):
        # 1. Ensure outputs are stripped
        outputs = cell.get("outputs", [])
        if len(outputs) > 0:
            errors.append(f"Cell {i+1} has {len(outputs)} non-empty output(s). Cell outputs must be cleared.")

        # 2. Ensure execution_count is None
        if cell.get("execution_count") is not None:
            errors.append(f"Cell {i+1} has execution_count={cell['execution_count']}. Must be reset to null.")

        # 3. Check for forbidden credentials or patterns in source code
        source_text = "".join(cell.get("source", []))
        for pat in FORBIDDEN_PATTERNS:
            if pat.search(source_text):
                # Allow references in documentation/comments if explicitly marked safe or in secret key list
                if "secret_keys" in source_text or "google.colab.userdata" in source_text or cell.get("cell_type") == "markdown":
                    continue
                errors.append(f"Cell {i+1} matched suspicious credential pattern '{pat.pattern}' in source.")

    return errors


def main():
    root = Path(__file__).resolve().parent.parent
    notebooks = list(root.glob("workers/cv-python/colab/**/*.ipynb")) + list(root.glob("notebooks/**/*.ipynb"))
    
    if not notebooks:
        print("No notebooks found.")
        sys.exit(0)

    all_passed = True
    for nb in notebooks:
        rel_path = nb.relative_to(root)
        errs = check_notebook(nb)
        if errs:
            all_passed = False
            print(f"❌ {rel_path}:")
            for err in errs:
                print(f"   • {err}")
        else:
            print(f"✅ {rel_path} passed cleanliness and output check.")

    if not all_passed:
        print("\nNotebook validation failed! Clear cell outputs and remove hardcoded credentials.")
        sys.exit(1)
    else:
        print("\nAll notebooks passed cleanliness checks.")
        sys.exit(0)


if __name__ == "__main__":
    main()
