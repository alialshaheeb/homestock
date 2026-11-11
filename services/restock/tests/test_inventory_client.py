"""The HTTP calls to the inventory service, against a mocked network (respx), no database."""
import httpx
import pytest
import respx

from app import inventory_client as client

BASE = "http://inventory.test"


@pytest.fixture(autouse=True)
def inventory_url(monkeypatch):
    monkeypatch.setenv("INVENTORY_URL", BASE + "/")  # trailing slash is tolerated
    monkeypatch.setenv("INVENTORY_TIMEOUT_S", "0.5")


@respx.mock
def test_low_stock_items_asks_inventory_with_the_filter():
    route = respx.get(f"{BASE}/items", params={"low_stock": "true"}).respond(json=[{"id": 1}])
    assert client.low_stock_items() == [{"id": 1}]
    assert route.called


@respx.mock
def test_get_item_returns_none_on_404():
    respx.get(f"{BASE}/items/5").respond(404, json={"detail": "item 5 not found"})
    assert client.get_item(5) is None


@respx.mock
def test_add_stock_posts_the_amount_and_reports_a_missing_item():
    ok = respx.post(f"{BASE}/items/1/restock").respond(json={"id": 1})
    respx.post(f"{BASE}/items/2/restock").respond(404)
    assert client.add_stock(1, 3) is True
    assert ok.calls.last.request.content == b'{"amount":3}'
    assert client.add_stock(2, 1) is False


@respx.mock
@pytest.mark.parametrize("failure", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")])
def test_network_failures_become_inventory_unavailable(failure):
    respx.get(f"{BASE}/items/1").mock(side_effect=failure)
    with pytest.raises(client.InventoryUnavailable):
        client.get_item(1)


@respx.mock
def test_server_errors_become_inventory_unavailable():
    respx.get(f"{BASE}/items").respond(503)
    with pytest.raises(client.InventoryUnavailable):
        client.low_stock_items()
