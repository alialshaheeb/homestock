"""HTTP-level tests: status codes and validation. Business rules are covered in test_inventory_service.py."""


def fridge(client):
    return next(loc["id"] for loc in client.get("/locations").json() if loc["name"] == "fridge")


def new_item(client, **fields):
    body = {"name": "milk", "location_id": fridge(client), **fields}
    response = client.post("/items", json=body)
    assert response.status_code == 201
    return response.json()


def test_locations_list_and_create(client):
    assert {loc["name"] for loc in client.get("/locations").json()} == {"fridge", "pantry", "toiletries"}
    assert client.post("/locations", json={"name": "freezer"}).status_code == 201
    assert client.post("/locations", json={"name": "freezer"}).status_code == 409


def test_item_crud_round_trip(client):
    item = new_item(client, quantity=2, unit="l", expiry_date="2026-11-20")
    assert client.get(f"/items/{item['id']}").json()["expiry_date"] == "2026-11-20"

    patched = client.patch(f"/items/{item['id']}", json={"quantity": 5}).json()
    assert patched["quantity"] == 5 and patched["unit"] == "l"  # unsent fields kept

    cleared = client.patch(f"/items/{item['id']}", json={"expiry_date": None}).json()
    assert cleared["expiry_date"] is None  # explicit null clears the date

    assert client.delete(f"/items/{item['id']}").status_code == 204
    assert client.get(f"/items/{item['id']}").status_code == 404


def test_validation_errors_return_422(client):
    loc = fridge(client)
    assert client.post("/items", json={"name": "", "location_id": loc}).status_code == 422
    assert client.post("/items", json={"name": "milk", "location_id": loc, "quantity": -1}).status_code == 422
    assert client.post("/items", json={"name": "milk", "location_id": loc, "expiry_date": "soon"}).status_code == 422


def test_unknown_location_is_404(client):
    assert client.post("/items", json={"name": "milk", "location_id": 999}).status_code == 404


def test_consume_and_restock_endpoints(client):
    item = new_item(client, quantity=1, min_threshold=1)
    assert client.get("/items", params={"low_stock": True}).json()[0]["id"] == item["id"]

    assert client.post(f"/items/{item['id']}/consume", json={"amount": 2}).status_code == 409
    assert client.post(f"/items/{item['id']}/consume", json={"amount": 0}).status_code == 422
    assert client.post(f"/items/{item['id']}/restock", json={"amount": 4}).json()["quantity"] == 5
    assert client.get("/items", params={"low_stock": True}).json() == []


def test_expiring_filter_rejects_negative_days(client):
    assert client.get("/items", params={"expiring_within_days": -1}).status_code == 422
