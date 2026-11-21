"""openapi.yaml is committed so the API can be read (and graded) without running the service.
This test fails if a route changes and the file was not regenerated with `python export_openapi.py`."""
from pathlib import Path

import yaml

from app.main import app

OPENAPI_FILE = Path(__file__).resolve().parent.parent / "openapi.yaml"


def test_committed_openapi_matches_the_code():
    committed = yaml.safe_load(OPENAPI_FILE.read_text(encoding="utf-8"))
    assert committed == app.openapi(), "the API changed: run `python export_openapi.py` and commit openapi.yaml"
