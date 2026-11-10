"""HTTP-level tests for /shopping-list, including the cross-domain flow end to end."""


def new_item(client, **fields):
    fridge = next(loc["id"] for loc in client.get("/locations").json() if loc["name"] == "fridge")
    return client.post("/items", json={"name": "milk", "location_id": fridge, **fields}).json()


def test_low_stock_to_bought_to_restocked(client):
    milk = new_item(client, quantity=0, min_threshold=1)
    added = client.post("/shopping-list/from-low-stock").json()
    assert len(added) == 1 and added[0]["quantity"] == 2

    bought = client.post(f"/shopping-list/{added[0]['id']}/bought")
    assert bought.status_code == 200 and bought.json()["restocked"] is True
    assert client.get(f"/items/{milk['id']}").json()["quantity"] == 2
    assert client.post(f"/shopping-list/{added[0]['id']}/bought").status_code == 409


def test_entry_crud_and_errors(client):
    created = client.post("/shopping-list", json={"name": "bread", "quantity": 1})
    assert created.status_code == 201
    entry_id = created.json()["id"]
    assert client.get(f"/shopping-list/{entry_id}").json()["name"] == "bread"
    assert client.patch(f"/shopping-list/{entry_id}", json={"quantity": 2}).json()["quantity"] == 2
    assert client.get("/shopping-list", params={"status": "open"}).json()[0]["id"] == entry_id
    assert client.delete(f"/shopping-list/{entry_id}").status_code == 204
    assert client.get(f"/shopping-list/{entry_id}").status_code == 404


def test_validation(client):
    assert client.post("/shopping-list", json={"name": "bread", "quantity": 0}).status_code == 422
    assert client.post("/shopping-list", json={"quantity": 1}).status_code == 409  # no name, no item
    assert client.post("/shopping-list", json={"quantity": 1, "inventory_item_id": 999}).status_code == 404
    assert client.get("/shopping-list", params={"status": "maybe"}).status_code == 422
