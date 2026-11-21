"""Integration test across the seam: the real restock service calling the real inventory service
over HTTP, each with its own SQL Server database, all started by docker compose (ADR-9).

Run it with the stack up, from the repository root:
    docker compose up -d --build
    pip install -r tests/integration/requirements.txt
    pytest tests/integration
The last test stops the inventory container for a moment and starts it again.
"""
import os
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import pytest

INVENTORY = os.environ.get("INVENTORY_BASE_URL", "http://localhost:8001")
RESTOCK = os.environ.get("RESTOCK_BASE_URL", "http://localhost:8002")
REPO_ROOT = Path(__file__).resolve().parents[2]


def wait_until_healthy(base_url: str, seconds: int = 180) -> None:
    deadline = time.monotonic() + seconds
    while True:
        try:
            if httpx.get(f"{base_url}/health", timeout=5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        if time.monotonic() > deadline:
            pytest.fail(f"{base_url}/health never returned 200")
        time.sleep(2)


def compose(*args: str) -> None:
    subprocess.run(["docker", "compose", *args], cwd=REPO_ROOT, check=True)


@pytest.fixture(scope="module", autouse=True)
def stack_is_up():
    wait_until_healthy(INVENTORY)
    wait_until_healthy(RESTOCK)


def new_item(**fields) -> dict:
    """Create an item in Inventory (the fridge is seeded by inventory's start-up)."""
    fridge = next(loc for loc in httpx.get(f"{INVENTORY}/locations").json() if loc["name"] == "fridge")
    body = {"name": f"it-{uuid.uuid4().hex[:8]}", "location_id": fridge["id"], **fields}
    response = httpx.post(f"{INVENTORY}/items", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_low_stock_item_goes_on_the_list_and_buying_it_restocks_inventory():
    item = new_item(quantity=0, unit="l", min_threshold=1)
    assert item["low_stock"] is True

    # Restock calls GET /items?low_stock=true on Inventory.
    added = httpx.post(f"{RESTOCK}/shopping-list/from-low-stock").json()
    entry = next(e for e in added if e["inventory_item_id"] == item["id"])
    assert (entry["name"], entry["unit"], entry["quantity"]) == (item["name"], "l", 2)  # 2 x threshold - quantity

    # Restock calls POST /items/{id}/restock on Inventory.
    bought = httpx.post(f"{RESTOCK}/shopping-list/{entry['id']}/bought")
    assert bought.status_code == 200 and bought.json()["restocked"] is True
    assert httpx.get(f"{INVENTORY}/items/{item['id']}").json()["quantity"] == 2


def test_adding_an_inventory_item_copies_its_name_and_unit():
    item = new_item(quantity=5, unit="kg")

    # Restock calls GET /items/{id} on Inventory, and copies what it displays (ADR-3).
    created = httpx.post(f"{RESTOCK}/shopping-list", json={"inventory_item_id": item["id"], "quantity": 3})
    assert created.status_code == 201, created.text
    assert (created.json()["name"], created.json()["unit"]) == (item["name"], "kg")

    # An id Inventory does not know is a 404 from Restock.
    missing = httpx.post(f"{RESTOCK}/shopping-list", json={"inventory_item_id": 999999, "quantity": 1})
    assert missing.status_code == 404


def test_with_inventory_stopped_restock_answers_503_and_the_list_still_works():
    compose("stop", "inventory")
    try:
        response = httpx.post(f"{RESTOCK}/shopping-list/from-low-stock", timeout=15)
        assert response.status_code == 503
        assert "inventory service is not reachable" in response.json()["detail"]
        assert httpx.get(f"{RESTOCK}/shopping-list").status_code == 200
        assert httpx.get(f"{RESTOCK}/health").status_code == 200  # Inventory's state is not part of it
    finally:
        compose("start", "inventory")
        wait_until_healthy(INVENTORY)
