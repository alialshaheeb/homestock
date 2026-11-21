"""Regenerate openapi.yaml from the code: `python export_openapi.py` (needs requirements-dev.txt).

openapi.yaml is committed so it can be read without running the service; a test checks
that it still matches the code, so a route change without a new export fails CI.
"""
from pathlib import Path

import yaml

from app.main import app

if __name__ == "__main__":
    Path("openapi.yaml").write_text(yaml.safe_dump(app.openapi(), sort_keys=False, allow_unicode=True), encoding="utf-8")
    print("wrote openapi.yaml")
