"""The ONLY place the restock service talks to the inventory service (the seam, ADR-2/ADR-6).

Every call is an HTTP request with a timeout. If Inventory is down, slow, or answers with
a server error, the call raises InventoryUnavailable, and the routes turn that into a
clear 503 instead of a stack trace or a hung request.
"""
import os

import httpx


class InventoryUnavailable(Exception):
    """The inventory service did not answer in time, or answered with a server error."""


def _base_url() -> str:
    return os.environ.get("INVENTORY_URL", "http://inventory:8000").rstrip("/")


def _timeout() -> float:
    return float(os.environ.get("INVENTORY_TIMEOUT_S", "2"))


def _request(method: str, path: str, **kwargs) -> httpx.Response:
    try:
        response = httpx.request(method, _base_url() + path, timeout=_timeout(), **kwargs)
    except httpx.HTTPError as error:  # connection refused, DNS failure, timeout...
        raise InventoryUnavailable(f"inventory service unreachable: {error.__class__.__name__}")
    if response.status_code >= 500:
        raise InventoryUnavailable(f"inventory service answered {response.status_code}")
    return response


def low_stock_items() -> list[dict]:
    response = _request("GET", "/items", params={"low_stock": "true"})
    response.raise_for_status()
    return response.json()


def get_item(item_id: int) -> dict | None:
    """The Inventory item, or None if it does not exist (any more)."""
    response = _request("GET", f"/items/{item_id}")
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def add_stock(item_id: int, amount: float) -> bool:
    """Increase an item's stock. False if the item no longer exists in Inventory."""
    response = _request("POST", f"/items/{item_id}/restock", json={"amount": amount})
    if response.status_code == 404:
        return False
    response.raise_for_status()
    return True
