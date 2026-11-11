"""HTTP-level tests for /shopping-list, including the designed failure when Inventory is down."""


def test_low_stock_to_bought_to_restocked(client, inventory):
    inventory.add(1, "milk", quantity=0, min_threshold=1)
    added = client.post("/shopping-list/from-low-stock").json()
    assert len(added) == 1 and added[0]["quantity"] == 2

    bought = client.post(f"/shopping-list/{added[0]['id']}/bought")
    assert bought.status_code == 200 and bought.json()["restocked"] is True
    assert inventory.items[1]["quantity"] == 2
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


def test_inventory_down_gives_a_clear_503_and_the_list_still_works(client, inventory):
    client.post("/shopping-list", json={"name": "bread", "quantity": 1})
    inventory.down = True
    response = client.post("/shopping-list/from-low-stock")
    assert response.status_code == 503
    assert "inventory service is not reachable" in response.json()["detail"]
    assert client.get("/shopping-list").status_code == 200
    assert client.get("/health").status_code == 200  # Inventory's state is not part of our health
